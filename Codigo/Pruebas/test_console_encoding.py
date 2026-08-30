import io
import logging
import sys
import unittest

ROOT = r"D:\Proyecto\Codigo\Crawler"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from console_encoding import configure_console_encoding


class ConsoleEncodingTests(unittest.TestCase):
    def test_reconfigures_legacy_stream_to_utf8_with_safe_fallback(self):
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
        try:
            configure_console_encoding((stream,))
            self.assertEqual(stream.encoding.lower().replace("-", ""), "utf8")
            self.assertEqual(stream.errors, "backslashreplace")

            handler = logging.StreamHandler(stream)
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger = logging.getLogger("test_console_encoding")
            logger.handlers[:] = [handler]
            logger.propagate = False
            logger.setLevel(logging.INFO)
            logger.info("Enseñanza‐aprendizaje 🔄")
            handler.flush()
            self.assertIn("Enseñanza".encode("utf-8"), raw.getvalue())
        finally:
            stream.detach()

    def test_stream_without_reconfigure_is_ignored(self):
        class EmbeddedStream:
            pass

        configure_console_encoding((EmbeddedStream(),))


if __name__ == "__main__":
    unittest.main()
