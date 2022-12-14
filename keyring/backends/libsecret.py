import logging

from ..util import properties
from ..backend import KeyringBackend
from ..credentials import SimpleCredential
from ..errors import (
    PasswordDeleteError,
    PasswordSetError,
    ExceptionRaisedContext,
    KeyringLocked,
)

available = False
try:
    import gi
    from gi.repository import Gio
    from gi.repository import GLib

    gi.require_version('Secret', '1')
    from gi.repository import Secret

    available = True
except (AttributeError, ImportError, ValueError):
    pass

log = logging.getLogger(__name__)


class Keyring(KeyringBackend):
    """libsecret Keyring"""

    appid = 'Python keyring library'
    if available:
        schema = Secret.Schema.new(
            "org.freedesktop.Secret.Generic",
            Secret.SchemaFlags.NONE,
            {
                "application": Secret.SchemaAttributeType.STRING,
                "service": Secret.SchemaAttributeType.STRING,
                "username": Secret.SchemaAttributeType.STRING,
            },
        )

    @properties.ClassProperty
    @classmethod
    def priority(cls):
        with ExceptionRaisedContext() as exc:
            Secret.__name__
        if exc:
            raise RuntimeError("libsecret required")
        return 4.8

    def get_password(self, service, username):
        """Get password of the username for the service"""
        attributes = {
            "application": self.appid,
            "service": service,
            "username": username,
        }
        try:
            items = Secret.password_search_sync(
                self.schema, attributes, Secret.SearchFlags.UNLOCK, None
            )
        except GLib.Error as error:
            quark = GLib.quark_try_string('g-io-error-quark')
            if error.matches(quark, Gio.IOErrorEnum.FAILED):
                raise KeyringLocked('Failed to unlock the item!') from error
            raise
        for item in items:
            try:
                return item.retrieve_secret_sync().get_text()
            except GLib.Error as error:
                quark = GLib.quark_try_string('secret-error')
                if error.matches(quark, Secret.Error.IS_LOCKED):
                    raise KeyringLocked('Failed to unlock the item!') from error
                raise

    def set_password(self, service, username, password):
        """Set password for the username of the service"""
        collection = Secret.COLLECTION_DEFAULT
        attributes = {
            "application": self.appid,
            "service": service,
            "username": username,
        }
        label = "Password for '{}' on '{}'".format(username, service)
        try:
            stored = Secret.password_store_sync(
                self.schema, attributes, collection, label, password, None
            )
        except GLib.Error as error:
            quark = GLib.quark_try_string('secret-error')
            if error.matches(quark, Secret.Error.IS_LOCKED):
                raise KeyringLocked("Failed to unlock the collection!") from error
            quark = GLib.quark_try_string('g-io-error-quark')
            if error.matches(quark, Gio.IOErrorEnum.FAILED):
                raise KeyringLocked("Failed to unlock the collection!") from error
            raise
        if not stored:
            raise PasswordSetError("Failed to store password!")

    def delete_password(self, service, username):
        """Delete the stored password (only the first one)"""
        attributes = {
            "application": self.appid,
            "service": service,
            "username": username,
        }
        try:
            items = Secret.password_search_sync(
                self.schema, attributes, Secret.SearchFlags.UNLOCK, None
            )
        except GLib.Error as error:
            quark = GLib.quark_try_string('g-io-error-quark')
            if error.matches(quark, Gio.IOErrorEnum.FAILED):
                raise KeyringLocked('Failed to unlock the item!') from error
            raise
        for item in items:
            try:
                removed = Secret.password_clear_sync(
                    self.schema, item.get_attributes(), None
                )
            except GLib.Error as error:
                quark = GLib.quark_try_string('secret-error')
                if error.matches(quark, Secret.Error.IS_LOCKED):
                    raise KeyringLocked('Failed to unlock the item!') from error
                raise
            return removed
        raise PasswordDeleteError("No such password!")

    def get_credential(self, service, username):
        """Get the first username and password for a service.
        Return a Credential instance

        The username can be omitted, but if there is one, it will use get_password
        and return a SimpleCredential containing  the username and password
        Otherwise, it will return the first username and password combo that it finds.
        """
        query = {"service": service}
        if username:
            query["username"] = username
        try:
            items = Secret.password_search_sync(
                self.schema, query, Secret.SearchFlags.UNLOCK, None
            )
        except GLib.Error as error:
            quark = GLib.quark_try_string('g-io-error-quark')
            if error.matches(quark, Gio.IOErrorEnum.FAILED):
                raise KeyringLocked('Failed to unlock the item!') from error
            raise
        for item in items:
            username = item.get_attributes().get("username")
            try:
                return SimpleCredential(
                    username, item.retrieve_secret_sync().get_text()
                )
            except GLib.Error as error:
                quark = GLib.quark_try_string('secret-error')
                if error.matches(quark, Secret.Error.IS_LOCKED):
                    raise KeyringLocked('Failed to unlock the item!') from error
                raise
