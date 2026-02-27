import os
from umls_downloader import download_umls

# Get this from https://uts.nlm.nih.gov/uts/edit-profile
api_key = "2deece55-3f14-4d61-b47e-3cacab1e4831"

path = download_umls(version="2025AB", api_key=api_key)

# This is where it gets downloaded: ~/.data/bio/umls/2021AB/umls-2021AB-mrconso.zip
expected_path = os.path.join(
    os.path.expanduser("~"),
    ".data",
    "umls",
    "2025AB",
    "umls-2025AB-mrsty.zip",
)
assert expected_path == path.as_posix()
