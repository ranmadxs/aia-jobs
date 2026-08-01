import os

BCI_SENDER = "bcimail@bci.cl"
DB_NAME = "bci"
COLLECTION = "cartolas"
BANK = "bci"

BCI_PDF_PASSWORD = os.getenv("BCI_PDF_PASSWORD", "")

MONGODB_URI_MAIN = os.getenv("MONGODB_URI_MAIN", "")