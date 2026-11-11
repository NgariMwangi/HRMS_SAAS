"""Run without the database fixtures: python -m unittest discover -s tests -p test_password_security.py."""
import unittest

from werkzeug.security import generate_password_hash

from app.core.security import hash_password, verify_password


class PasswordSecurityTests(unittest.TestCase):
    def test_existing_bcrypt_and_new_passwords(self):
        hashed = hash_password("SaaS-password-123")
        self.assertTrue(hashed.startswith("$2b$"))
        self.assertTrue(verify_password("SaaS-password-123", hashed))
        self.assertFalse(verify_password("wrong-password", hashed))

    def test_imported_werkzeug_hashes(self):
        for method in ("scrypt:32768:8:1", "pbkdf2:sha256:600000"):
            for password in ("Original-password-123", "long-password-" * 8, "P?ssw?rd-??"):
                with self.subTest(method=method, password_length=len(password)):
                    hashed = generate_password_hash(password, method=method)
                    self.assertTrue(verify_password(password, hashed))
                    self.assertFalse(verify_password("wrong-password", hashed))

    def test_invalid_hashes_fail_authentication(self):
        for hashed in ("", "plaintext", "$2b$broken", "scrypt:broken$salt$hash",
                       "pbkdf2:sha256:broken$salt$hash", "unknown$salt$hash"):
            with self.subTest(hashed=hashed):
                self.assertFalse(verify_password("password", hashed))
