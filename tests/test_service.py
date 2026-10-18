"""
Unit tests for the Elasticsearch DXL service which do not require a running
Elasticsearch server or DXL broker.
"""
import json
import os
import shutil
import tempfile
import unittest

from mock import MagicMock

from dxlclient.message import Event
from dxlelasticsearchservice import ElasticsearchService
from dxlelasticsearchservice._requesthandlers import \
    ElasticsearchServiceEventCallback

SAMPLE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample")
TRANSFORM_SCRIPT = os.path.join(SAMPLE_DIR,
                                "advanced_transform_example_script.py")

APP_CONFIG = """[General]
serverNames=es1,es2
eventGroupNames=eventgroup1
apiNames=index,get,not_an_api_method

[es1]
host=es1.example.local
port=9201
useSSL=yes
verifyCertificate=no
user=elastic
password=test

[es2]
host=es2.example.local

[eventgroup1]
topics=/sample/topic1,/sample/topic2
documentIndex=test-index
documentType=test-doc
idFieldName=event_id
"""


class ElasticsearchServiceTest(unittest.TestCase):

    def setUp(self):
        self.config_dir = tempfile.mkdtemp()
        with open(os.path.join(self.config_dir,
                               "dxlelasticsearchservice.config"), "w") as f:
            f.write(APP_CONFIG)

    def tearDown(self):
        shutil.rmtree(self.config_dir)

    def test_load_configuration(self):
        app = ElasticsearchService(self.config_dir)
        app._load_configuration()

        es1 = app._get_server_settings("es1")
        self.assertEqual(es1["host"], "es1.example.local")
        self.assertEqual(es1["port"], 9201)
        self.assertTrue(es1["use_ssl"])
        self.assertFalse(es1["verify_certs"])
        self.assertEqual(es1["http_auth"], ("elastic", "test"))
        self.assertIsNone(es1["ssl_assert_hostname"])

        es2 = app._get_server_settings("es2")
        self.assertEqual(es2["host"], "es2.example.local")
        self.assertNotIn("port", es2)
        self.assertNotIn("http_auth", es2)

        self.assertEqual(["index", "get", "not_an_api_method"],
                         app._api_names)
        self.assertEqual(
            ["/sample/topic1", "/sample/topic2"],
            app._event_groups["eventgroup1"]["topics"])
        self.assertEqual("event_id",
                         app._event_groups["eventgroup1"]["id_field_name"])

        # The Elasticsearch client is created from the configured servers
        # without contacting them
        self.assertIsNotNone(app._es_client)
        self.assertTrue(callable(app._get_api_method("index")))
        self.assertTrue(callable(app._get_api_method("get")))
        self.assertIsNone(app._get_api_method("not_an_api_method"))

    def test_missing_server_host_raises(self):
        with open(os.path.join(self.config_dir,
                               "dxlelasticsearchservice.config"), "w") as f:
            f.write("[General]\nserverNames=es1\n\n[es1]\nport=9200\n")
        app = ElasticsearchService(self.config_dir)
        with self.assertRaises(ValueError):
            app._load_configuration()

    def test_event_callback_indexes_payload(self):
        es_client = MagicMock()
        callback = ElasticsearchServiceEventCallback(
            es_client, "eventgroup1", "test-index", "test-doc", "event_id",
            None, False)

        event = Event("/sample/topic1")
        event.payload = json.dumps({"event_id": "abc", "message": "hello"}).encode("utf-8")
        callback.on_event(event)

        es_client.index.assert_called_once_with(
            index="test-index", doc_type="test-doc",
            body={"event_id": "abc", "message": "hello"}, id="abc")

    def test_event_callback_with_transform_script(self):
        es_client = MagicMock()
        callback = ElasticsearchServiceEventCallback(
            es_client, "advanced_transform_example", "test-index", "test-doc",
            None, TRANSFORM_SCRIPT, False)

        event = Event("/sample/topic1")
        event.payload = b"plain text payload"
        callback.on_event(event)

        # The sample transform script turns one event into two documents
        self.assertEqual(2, es_client.index.call_count)
        ids = sorted(call.kwargs["id"] for call in es_client.index.call_args_list)
        self.assertEqual(["advanced-event-example-id-1",
                          "advanced-event-example-id-2"], ids)
        for call in es_client.index.call_args_list:
            self.assertEqual("test-index", call.kwargs["index"])
            self.assertEqual("test-doc", call.kwargs["doc_type"])
            self.assertEqual("plain text payload",
                             json.loads(call.kwargs["body"])["message"])

    def test_event_callback_skips_invalid_json_payload(self):
        es_client = MagicMock()
        callback = ElasticsearchServiceEventCallback(
            es_client, "eventgroup1", "test-index", "test-doc", None,
            None, False)

        event = Event("/sample/topic1")
        event.payload = b"not valid json"
        callback.on_event(event)

        es_client.index.assert_not_called()

    def test_event_callback_skips_missing_id_field(self):
        es_client = MagicMock()
        callback = ElasticsearchServiceEventCallback(
            es_client, "eventgroup1", "test-index", "test-doc", "event_id",
            None, False)

        event = Event("/sample/topic1")
        event.payload = json.dumps({"message": "missing id"}).encode("utf-8")
        callback.on_event(event)

        es_client.index.assert_not_called()


if __name__ == "__main__":
    unittest.main()
