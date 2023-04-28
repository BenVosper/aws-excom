from botocore import exceptions

BOTOCORE_EXCEPTIONS = [
    obj for obj in exceptions.__dict__.values() if isinstance(obj, type)
]
