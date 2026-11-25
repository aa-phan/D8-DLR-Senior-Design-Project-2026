import unittest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time

class mainTest(unittest.TestCase):
    def setUp(self):
        self.browser = webdriver.Firefox()

    def tearDown(self):
        self.browser.quit()
    
    def test_mainTest(self):
        self.browser.get("http://localhost:8000")

        self.assertIn("Dynamic Line Rating", self.browser.title)

        

if __name__ == "__main__":
    unittest.main()