DISCONNECT_MESSAGE = 'Message recipient disconnected from message bus without replying'
UNKNOWN_METHOD = 'org.freedesktop.DBus.Error.UnknownMethod'
NO_REPLY = 'org.freedesktop.DBus.Error.NoReply'


def released_connection_rejected(completion, errors, replies, name_owned):
    if name_owned is not False:
        return False
    if completion == [UNKNOWN_METHOD]:
        return True
    return (
        completion == [NO_REPLY]
        and len(errors) == 1
        and errors[0] == {
            'domain': 'g-dbus-error-quark',
            'code': 4,
            'message': 'GDBus.Error:' + NO_REPLY + ': ' + DISCONNECT_MESSAGE,
        }
        and any(reply == {
            'sender': 'org.freedesktop.DBus',
            'error': NO_REPLY,
            'body': [DISCONNECT_MESSAGE],
        } for reply in replies)
    )
