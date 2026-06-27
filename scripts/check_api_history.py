import os
import requests

TRESTLE_URL = "https://api-trestle.corelogic.com/trestle/odata/Property"
AUTH_ENDPOINT = os.environ.get("TRESTLE_AUTH_ENDPOINT")

if not AUTH_ENDPOINT:
    raise SystemExit("Missing TRESTLE_AUTH_ENDPOINT. Set it in your terminal first.")

token_response = requests.get(AUTH_ENDPOINT, timeout=30)
token_response.raise_for_status()

token = token_response.json().get("access_token")
if not token:
    raise SystemExit("Could not retrieve access_token.")

headers = {"Authorization": f"Bearer {token}"}


def check_year(year):
    start = f"{year}-01-01T00:00:00.000Z"
    end = f"{year + 1}-01-01T00:00:00.000Z"

    # Do NOT filter PropertySubType here.
    # PropertySubType behaves like an enum in the API and rejects "Single Family Residence".
    odata_filter = (
        "MlsStatus eq 'Closed' "
        f"and CloseDate ge {start} "
        f"and CloseDate lt {end} "
        "and PropertyType eq 'Residential'"
    )

    params = {
        "$select": "ListingKey,CloseDate,ClosePrice,ListOfficeName,PropertyType,PropertySubType",
        "$filter": odata_filter,
        "$top": 1,
    }

    response = requests.get(
        TRESTLE_URL,
        params=params,
        headers=headers,
        timeout=60,
    )

    if response.status_code != 200:
        return {
            "year": year,
            "available": False,
            "status_code": response.status_code,
            "sample_close_date": None,
            "sample_subtype": None,
            "error": response.text[:500],
        }

    data = response.json()
    rows = data.get("value", [])

    if rows:
        return {
            "year": year,
            "available": True,
            "status_code": response.status_code,
            "sample_close_date": rows[0].get("CloseDate"),
            "sample_subtype": rows[0].get("PropertySubType"),
            "error": None,
        }

    return {
        "year": year,
        "available": False,
        "status_code": response.status_code,
        "sample_close_date": None,
        "sample_subtype": None,
        "error": None,
    }


results = []

for year in range(2000, 2026):
    result = check_year(year)
    results.append(result)

    if result["available"]:
        print(
            f"{year}: AVAILABLE | "
            f"sample CloseDate = {result['sample_close_date']} | "
            f"sample PropertySubType = {result['sample_subtype']}"
        )
    else:
        print(
            f"{year}: not available | "
            f"status = {result['status_code']} | "
            f"error = {result['error']}"
        )

available_years = [r["year"] for r in results if r["available"]]

print("\n--- Summary ---")
if available_years:
    print(f"Earliest available year: {min(available_years)}")
    print(f"Latest available year: {max(available_years)}")
else:
    print("No years returned data. Check token, filters, or API access.")