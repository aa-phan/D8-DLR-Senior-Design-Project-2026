"""
PSS/E hourly job (pss-e-integration). Runs on the licensed laptop under PSS/E's Python,
so every module here uses only the standard library (psycopg is imported lazily by the
writer) and Python 3.7 syntax; it must not import backend/config.py or any other backend
module (D-05).
"""
