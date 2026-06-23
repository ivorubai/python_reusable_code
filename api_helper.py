
#!/usr/bin/python
import requests
import logging
import time
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class APIHelper:

    def __init__(self, ip, base_api):
        """
        Initialize the APIHelper with the base URL for the API.
        """
        self.ip = ip
        self.base_api = base_api
        self.base_url = 'https://' + ip + base_api
        self.session = requests.Session()  # Create a session object to manage requests
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

    def _request(self, method, endpoint, log=True, raise_on_status=True, **kwargs):
        """
        A helper function to make HTTP requests, ensuring session is active.

        """
        url = f"{self.base_url}{endpoint}"
        resp = self.session.request(method, url=url, verify=False, **kwargs)


        if log:
            self.logger.info("\n==== Request Info ====")
            self.logger.info("Method :", resp.request.method)
            self.logger.info("URL    :", resp.request.url)
            self.logger.info("Headers:", resp.request.headers)
            self.logger.info("Body   :", resp.request.body)

            self.logger.info("\n===== RESPONSE INFO =====")

            self.logger.info("Status :", resp.status_code)
            self.logger.info("URL    :", resp.url)
            self.logger.info("OK     :", resp.ok)

            self.logger.info("\n==== Response Body ====")
            try:
                self.logger.info(resp.json())
            except:
                self.logger.info(resp.text)
        if raise_on_status:
            resp.raise_for_status()
        return resp

    def get(self, endpoint, **kwargs):
        """Makes a GET request."""
        return self._request("GET", endpoint, **kwargs)

    def post(self, endpoint, **kwargs):
        """Makes a POST request."""
        return self._request("POST", endpoint, **kwargs)

    def put(self, endpoint, **kwargs):
        """Makes a PUT request."""
        return self._request("PUT", endpoint, **kwargs)

    def delete(self, endpoint, **kwargs):
        """Makes a DELETE request."""
        return self._request("DELETE", endpoint, **kwargs)

    def patch(self, endpoint, **kwargs):
        """Makes a PATCH request."""
        return self._request("PATCH", endpoint, **kwargs)

