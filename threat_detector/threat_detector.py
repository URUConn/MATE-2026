"""
threat_detector.py — MATE 2026 Task 2.2 Iceberg Tracking.

Given one iceberg (longitude, latitude, heading, keel depth) and four oil
platforms (name, longitude, latitude, water depth), report each platform's:

  * Surface-platform threat (green / yellow / red), from the iceberg's
    closest point of approach along its heading. Override: if the keel is
    >= 110% of local water depth the iceberg grounds first -> green.

  * Subsea-asset threat (green / yellow / red), from keel depth vs. local
    water depth, evaluated only for platforms passed within 25 nmi.

Geometry (per the manual): 1 minute of latitude = 1 nmi, so 1 deg lat = 60
nmi and 1 deg lon = 60 * cos(lat) nmi. Heading is a compass bearing
(0 = North, 90 = East).

https://20693798.fs1.hubspotusercontent-na1.net/hubfs/20693798/2026/Supporting%20Documents/Iceberg%20Information%20Examples%20EX%20PN%20RN%20Updated%202_16.pdf
^^^^ Link to example platform data and expected results
"""

import math

NUM_PLATFORMS = 4
RED_NMI = 5.0            # CPA < 5 nmi          -> red
YELLOW_NMI = 10.0        # CPA 5-10 nmi         -> yellow ; > 10 -> green
SUBSEA_RANGE_NMI = 25.0  # subsea threat only evaluated within this range


def read_dms(prompt):
    print(prompt)
    deg = float(input("  Degrees: "))
    minutes = float(input("  Minutes: "))
    seconds = float(input("  Seconds: "))
    sign = 1.0

    hemi = input("  Hemisphere (N/S/E/W): ").strip().upper()
    if hemi in ["S", "W"]:
        sign = -1.0

    return sign * (deg + minutes / 60.0 + seconds / 3600.0)


def read_iceberg():
    print("--- Iceberg ---")
    lat = read_dms("Latitude (DMS):")
    lon = read_dms("Longitude (DMS):")
    heading = float(input("Heading (deg, 0=N, 90=E): "))
    keel = abs(float(input("Keel depth (m): ")))
    return {"lon": lon, "lat": lat, "heading": heading, "keel": keel}


def read_platforms():
    platforms = []
    for i in range(NUM_PLATFORMS):
        print(f"--- Platform {i + 1} ---")
        name = input("Name: ")
        lat = float(input("Latitude: "))
        lon = float(input("Longitude: "))
        depth = abs(float(input("Water depth (m): ")))  # entered with any sign
        platforms.append({"name": name, "lon": lon, "lat": lat, "depth": depth})
    return platforms




def closest_approach(ice, plat):
    """Distance (nmi) at the iceberg's closest point of approach to a platform.
    If the platform is abeam or behind the iceberg, returns current distance."""
    mean_lat = math.radians((ice["lat"] + plat["lat"]) / 2.0)
    east = (plat["lon"] - ice["lon"]) * 60.0 * math.cos(mean_lat)
    north = (plat["lat"] - ice["lat"]) * 60.0

    hr = math.radians(ice["heading"])
    hx, hy = math.sin(hr), math.cos(hr)   # heading unit vector (east, north)

    t = east * hx + north * hy            # projection of platform onto track
    if t <= 0:
        return math.hypot(east, north)    # platform abeam/behind iceberg

    return math.hypot(east - t * hx, north - t * hy)


def surface_threat(ice, plat, cpa):
    if plat["depth"] > 0 and ice["keel"] >= plat["depth"] * 1.10:
        return "Green"                    # grounds before reaching platform
    if cpa > YELLOW_NMI:
        return "Green"
    if cpa >= RED_NMI:
        return "Yellow"
    return "Red"


def subsea_threat(ice, plat, cpa):
    if cpa > SUBSEA_RANGE_NMI or plat["depth"] == 0:
        return "Green - does not intersect"                     
    ratio = ice["keel"] / plat["depth"]
    if ratio >= 1.10:
        return "Green"                    # grounds before reaching assets
    if ratio >= 0.90:
        return "Red"                      # 90-110% -> critical danger
    if ratio >= 0.70:
        return "Yellow"                   # 70-90%  -> caution
    return "Green"                        # < 70%   -> never reaches assets


def report(ice, platforms):
    print("\n" + "-" * 64)
    print(f"{'Platform':12} | {'CPA (nmi)':9} | {'Surface':8} | {'Subsea':8}")
    print("-" * 64)
    for plat in platforms:
        cpa = closest_approach(ice, plat)
        surf = surface_threat(ice, plat, cpa)
        sub = subsea_threat(ice, plat, cpa)
        print(f"{plat['name']:12} | {cpa:9.1f} | {surf:8} | {sub:8}")
    print("-" * 64)



if __name__ == "__main__":
    iceberg = read_iceberg()
    platforms = read_platforms()
    report(iceberg, platforms)
