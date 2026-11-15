
# import asf_search as asf

# # Initial search area around Sermeq Kujalleq
# bbox = [-50.6, 68.9, -49.2, 69.4]

# w, s, e, n = bbox
# wkt = (
#     f"POLYGON(({w} {s},{e} {s},{e} {n},"
#     f"{w} {n},{w} {s}))"
# )

# results = asf.search(
#     platform=["NISAR"],
#     processingLevel=["GOFF"],
#     intersectsWith=wkt,
#     start="2026-06-17",
#     end="2026-11-14",
#     maxResults=250,
# )

# print(f"Found {len(results)} GOFF products")

# for item in results:
#     p = item.properties
#     print(
#         p.get("sceneName", "Unknown"),
#         "|", p.get("startTime"),
#         "|", p.get("flightDirection"),
#     )


import asf_search as asf

# Search area around Brunt Ice Shelf, Antarctica
# Initial approximate area, not an exact terminus boundary
bbox = [-28.5, -75.8, -25.5, -74.8]

w, s, e, n = bbox

wkt = (
    f"POLYGON(({w} {s},{e} {s},{e} {n},"
    f"{w} {n},{w} {s}))"
)

results = asf.search(
    platform=["NISAR"],
    processingLevel=["GCOV"],
    intersectsWith=wkt,
    start="2026-06-17",
    end="2026-11-14",
    maxResults=250,
)

print(f"Found {len(results)} GCOV products")

for item in results:
    p = item.properties

    print(
        p.get("sceneName", "Unknown"),
        "|", p.get("startTime"),
        "|", p.get("flightDirection"),
        "|", p.get("polarization"),
    )


#     before_id = (
#     "NISAR_L2_PR_GCOV_023_066_D_125_0005_NASV_A_"
#     "20260618T192501_20260618T192538_P05023_N_F_J_001"
# )

# after_id = (
#     "NISAR_L2_PR_GCOV_032_066_D_125_0005_NASV_A_"
#     "20261004T192457_20261004T192534_P05023_N_F_J_001"
# )

# for item in results:
#     if item.properties.get("sceneName") in (before_id, after_id):
#         print("\nProduct:", item.properties["sceneName"])
#         print("Geometry:", item.geometry)
#         print("File:", item.properties.get("fileName"))
#         print("URL:", item.properties.get("url"))


#         from shapely.geometry import shape, Point

# # Approximate location near Brunt Ice Shelf
# terminus = Point(-27.4, -75.54)

# matching = []

# for item in results:
#     polygon = shape(item.geometry)

#     if polygon.covers(terminus):
#         matching.append(item)

# print(f"Products covering the point: {len(matching)}")

# for item in matching:
#     p = item.properties
#     print(
#         p.get("sceneName"),
#         "|", p.get("startTime"),
#         "|", p.get("flightDirection"),
#     )


before_id = "NISAR_L2_PR_GCOV_023_109_D_126_0005_NASV_A_20260621T190039_20260621T190115_P05023_N_F_J_001"
after_id = "NISAR_L2_PR_GCOV_033_109_D_126_0005_NASV_A_20261019T190035_20261019T190112_P05023_N_F_J_001"

from shapely.geometry import shape

selected = {
    item.properties["sceneName"]: item
    for item in results
    if item.properties["sceneName"] in (before_id, after_id)
}

before = shape(selected[before_id].geometry)
after = shape(selected[after_id].geometry)

overlap = before.intersection(after)

print("Before area:", before.area)
print("After area:", after.area)
print("Overlap:", overlap.area)
print("Overlap percentage:", round(
    overlap.area / min(before.area, after.area) * 100, 2
))