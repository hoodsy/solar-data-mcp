"""Tiny CSV datasets shared by the market tests."""

CANONICAL_TTS = (
    "state,year,price_per_watt,size_kw,module_manufacturer\n"
    "CO,2024,3.10,7.2,Qcells\n"
    "CO,2023,3.40,6.1,Qcells\n"
    "AZ,2024,2.60,8.0,First Solar\n"
)

SOLARTRACE_CSV = (
    "state,jurisdiction,median_permit_days,median_inspection_days,median_pto_days\n"
    "CO,Boulder County,12,5,21\n"
    "CO,Denver,8,4,14\n"
    "AZ,Maricopa County,6,3,10\n"
)
