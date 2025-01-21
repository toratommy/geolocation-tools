# geolocation-tools
Repository of utility functions for performing geospatial analytics.

**Functions include:**
- `reverse_geocode_geojson_to_dataframe`: Reverse geocodes latitude/longitude coordinates from a GeoJSON file into addresses formatted as '123 Main St, Seattle, WA 10001' using the Google Geocoder and returns a DataFrame with all original fields plus the new address field.
- `get_redfin_estimate`: scrapes redfin property value estimates using the following methodology:
    1. Opens https://www.redfin.com/what-is-my-home-worth
    2. Locates the text box with placeholder='Enter your address'.
    3. Types the given address.
    4. Clicks the 'Next' button (<button><span>Next</span></button>).
    5. Checks if a 'Did You Mean' popup appears (multiple address suggestions).
       - If so, clicks the first suggested address.
    6. Attempts to find the Redfin Estimate in an element with data-rf-test-name="avmValue".
    Returns the estimate string or None if not found/errored.
