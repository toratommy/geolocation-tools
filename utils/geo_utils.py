import pandas as pd
from geopy.geocoders import GoogleV3
from geopy.exc import GeocoderTimedOut
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException
)
import random
import logging

def reverse_geocode_geojson_to_dataframe(geojson_data, api_key, sample_size=100):
    """
    Reverse geocodes latitude/longitude coordinates from a GeoJSON file into addresses
    formatted as '123 Main St, Seattle, WA 10001' using the Google Geocoder and returns a 
    DataFrame with all original fields plus the new address field.

    Args:
        geojson_data (dict): Dictionary containing imported GeoJSON data.
        api_key (str): Google Maps API key.
        sample_size (int): Number of records to randomly sample from GeoJSON features.

    Returns:
        pd.DataFrame: A DataFrame containing all original fields plus the new address field.
    """
    # Initialize geolocator with GoogleV3
    geolocator = GoogleV3(api_key=api_key)
    
    # Extract features
    features = geojson_data.get("features", [])
    if sample_size and len(features) > sample_size:
        features = random.sample(features, sample_size)  # Randomly sample from features
    results = []

    for feature in features:
        # Extract geometry and properties
        properties = feature.get("properties", {})
        coords = feature.get("geometry", {}).get("coordinates", None)
        if coords and len(coords) >= 2:
            longitude, latitude = coords[:2]  # GeoJSON uses [longitude, latitude] format
            try:
                # Perform reverse geocoding
                location = geolocator.reverse((latitude, longitude), timeout=10)
                if location:
                    # Extract components for formatting
                    address_components = location.raw.get("address_components", [])
                    formatted_address = format_google_address(address_components)
                else:
                    formatted_address = "Address not found"
            except GeocoderTimedOut:
                formatted_address = "Geocoder timed out"
            
            # Add result with original properties and new fields
            result = properties.copy()
            result.update({
                "latitude": latitude,
                "longitude": longitude,
                "address": formatted_address
            })
            results.append(result)
    
    # Convert results to DataFrame
    df = pd.DataFrame(results)
    return df

def format_google_address(address_components):
    """
    Formats address components from Google Geocoder response into
    '123 Main St, Seattle, WA 10001'.

    Args:
        address_components (list): List of address components from Google Geocoder.

    Returns:
        str: Formatted address string.
    """
    # Map Google address components to required fields
    street_number = ""
    route = ""
    city = ""
    state = ""
    postcode = ""
    
    for component in address_components:
        types = component["types"]
        if "street_number" in types:
            street_number = component["long_name"]
        if "route" in types:
            route = component["long_name"]
        if "locality" in types:  # City
            city = component["long_name"]
        if "administrative_area_level_1" in types:  # State
            state = component["short_name"]
        if "postal_code" in types:
            postcode = component["long_name"]
    
    # Combine fields into formatted address
    return f"{street_number} {route}, {city}, {state} {postcode}".strip()

def get_redfin_estimate(address, driver_path, headless=True):
    """
    1. Opens https://www.redfin.com/what-is-my-home-worth
    2. Locates the text box with placeholder='Enter your address'.
    3. Types the given address.
    4. Clicks the 'Next' button (<button><span>Next</span></button>).
    5. Checks if a 'Did You Mean' popup appears (multiple address suggestions).
       - If so, clicks the first suggested address.
    6. Attempts to find the Redfin Estimate in an element with data-rf-test-name="avmValue".
    Returns the estimate string or None if not found/errored.
    """
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")

    # Use a typical desktop UA to reduce detection
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/109.0.0.0 Safari/537.36"
    )
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = None
    try:
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)

        url = "https://www.redfin.com/what-is-my-home-worth"
        logging.info(f"Navigating to {url}")
        driver.get(url)

        # 1) Close any cookie banner if present
        try:
            cookie_btn = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, ".onetrust-close-btn-handler"))
            )
            cookie_btn.click()
            logging.info("Closed cookie banner.")
        except TimeoutException:
            logging.info("No cookie banner or not clickable within 5s.")

        # 2) Wait for the "Enter your address" input
        try:
            address_box = WebDriverWait(driver, 2).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "input[placeholder='Enter your address']"))
            )
            logging.info("Found the address input box.")
        except TimeoutException:
            logging.warning("Timed out waiting for the address input box.")
            driver.save_screenshot("debug_no_address_box.png")
            return None

        # 3) Enter the address
        address_box.clear()
        address_box.send_keys(address)
        logging.info(f"Entered address: {address}")

        # Short wait for the site to process the input
        time.sleep(2)

        # 4) Click the 'Next' button
        try:
            next_btn = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.XPATH, "//button[span[text()='Next']]"))
            )
            next_btn.click()
            logging.info("Clicked 'Next' button.")
        except TimeoutException:
            logging.warning("The 'Next' button never became clickable. Attempting JS fallback.")
            try:
                fallback_btn = driver.find_element(By.XPATH, "//button[span[text()='Next']]")
                driver.execute_script("arguments[0].click();", fallback_btn)
                logging.info("Forced JS click on 'Next' button.")
            except NoSuchElementException:
                logging.error("Could not find any element matching //button[span[text()='Next']].")
                driver.save_screenshot("debug_no_next_button.png")
                return None

        # 5) Handle the 'Did You Mean' popup if it appears
        time.sleep(2)
        try:
            popup = WebDriverWait(driver, 2).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, '[data-rf-test-name="dialogGutsNode"]'))
            )
            logging.info("Detected 'Did You Mean' popup.")

            # Click the first suggested address
            try:
                addresses = popup.find_elements(By.CSS_SELECTOR, "div.item-row[data-rf-test-name='item-row-active']")
                if addresses:
                    addresses[0].click()
                    logging.info("Clicked the first suggested address.")
                else:
                    # Optionally close the popup
                    close_btn = popup.find_element(By.CSS_SELECTOR, "button[data-rf-test-name='dialog-close-button']")
                    close_btn.click()
                    logging.info("No suggestions found; closed the popup.")
            except NoSuchElementException:
                logging.warning("No suggestions or close button found in the popup.")
        except TimeoutException:
            logging.info("No 'Did You Mean' popup appeared within 3s, continuing.")

        # Wait for the page to update/navigate
        time.sleep(2)

        # 6) Attempt to find a Redfin Estimate (only attempt #3: data-rf-test-name="avmValue")
        try:
            estimate_el = driver.find_element(By.CSS_SELECTOR, '[data-rf-test-name="avmValue"]')
            estimate_text = estimate_el.text.strip()
            logging.info(f"Redfin Estimate found (avmValue): {estimate_text}")
            return estimate_text
        except NoSuchElementException:
            logging.warning("No element found with [data-rf-test-name='avmValue'].")
            logging.warning("No known estimate elements found.")
            return None

    except WebDriverException as e:
        logging.error(f"WebDriver error: {e}")
        return None
    finally:
        if driver:
            driver.quit()
            logging.info("WebDriver quit.")