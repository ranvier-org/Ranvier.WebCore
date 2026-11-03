import copy
import unittest

from protocol_errors import DISCONNECT_MESSAGE, NO_REPLY, UNKNOWN_METHOD, released_connection_rejected


class ReleasedConnectionTests(unittest.TestCase):
    def setUp(self):
        self.args = [[NO_REPLY], [{'domain': 'g-dbus-error-quark', 'code': 4,
            'message': 'GDBus.Error:' + NO_REPLY + ': ' + DISCONNECT_MESSAGE}],
            [{'sender': 'org.freedesktop.DBus', 'error': NO_REPLY, 'body': [DISCONNECT_MESSAGE]}], False]

    def test_exact_bus_disconnect_after_name_loss(self):
        self.assertTrue(released_connection_rejected(*self.args))

    def test_unregister_rejection(self):
        self.assertTrue(released_connection_rejected([UNKNOWN_METHOD], [], [], False))

    def test_unregister_error_without_name_loss_rejects(self):
        self.assertFalse(released_connection_rejected([UNKNOWN_METHOD], [], [], True))

    def test_success_and_empty_and_other_errors_reject(self):
        for completion in [['success'], [], ['org.freedesktop.DBus.Error.Timeout'], [NO_REPLY, NO_REPLY]]:
            with self.subTest(completion=completion):
                args = copy.deepcopy(self.args)
                args[0] = completion
                self.assertFalse(released_connection_rejected(*args))

    def test_still_owned_name_rejects_disconnect(self):
        args = copy.deepcopy(self.args)
        args[3] = True
        self.assertFalse(released_connection_rejected(*args))

    def test_timeout_text_rejects(self):
        args = copy.deepcopy(self.args)
        args[1][0]['message'] = 'GDBus.Error:' + NO_REPLY + ': Message did not receive a reply (timeout by message bus)'
        self.assertFalse(released_connection_rejected(*args))

    def test_wrong_sender_or_body_rejects(self):
        for field, value in [('sender', ':1.2'), ('body', ['timeout']), ('error', UNKNOWN_METHOD)]:
            args = copy.deepcopy(self.args)
            args[2][0][field] = value
            self.assertFalse(released_connection_rejected(*args))

    def test_missing_reply_or_error_rejects(self):
        for index in [1, 2]:
            args = copy.deepcopy(self.args)
            args[index] = []
            self.assertFalse(released_connection_rejected(*args))


if __name__ == '__main__':
    unittest.main()
