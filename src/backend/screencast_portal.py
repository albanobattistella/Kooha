# SPDX-FileCopyrightText: Copyright 2018-2021 Jonas Adahl
# SPDX-FileCopyrightText: Copyright 2021 SeaDve
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from gi.repository import GObject, GLib, Gio

from kooha.widgets.area_selector import Screen

logger = logging.getLogger(__name__)


class ScreencastPortal(GObject.GObject):
    __gsignals__ = {'ready': (GObject.SIGNAL_RUN_FIRST, None, (int, int, object, bool)),
                    'cancelled': (GObject.SIGNAL_RUN_FIRST, None, (str,))}

    def __init__(self):
        super().__init__()

        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.proxy = Gio.DBusProxy.new_sync(
            self.bus,
            Gio.DBusProxyFlags.NONE,
            None,
            'org.freedesktop.portal.Desktop',
            '/org/freedesktop/portal/desktop',
            'org.freedesktop.portal.ScreenCast',
            None
        )

        self.sender_name = self.bus.get_unique_name()[1:].replace('.', '_')
        self.request_counter = 0
        self.session_counter = 0

    def _on_create_session_response(self, bus, sender, path, request_path, node, output):
        response, results = output
        if response != 0:
            self.emit('cancelled', _("Failed to create session."))
            logger.warning(f"Failed to create session: {response}")
            return

        self.session_handle = results['session_handle']
        logger.info("Session created")
        self._screencast_call(
            self.proxy.SelectSources,
            self._on_select_sources_response,
            '(oa{sv})',
            self.session_handle,
            options={
                'types': GLib.Variant('u', 1 if self.is_selection_mode else 1 | 2),
                'cursor_mode': GLib.Variant('u', 2 if self.is_show_pointer else 1)
            }
        )

    def _on_select_sources_response(self, bus, sender, path, request_path, node, output):
        response, results = output
        if response != 0:
            self.emit('cancelled', _("Failed to select sources."))
            logger.warning(f"Failed to select sources: {response}")
            return

        logger.info("Sources selected")
        self._screencast_call(
            self.proxy.Start,
            self._on_start_response,
            '(osa{sv})',
            self.session_handle,
            ''
        )

    def _on_start_response(self, bus, sender, path, request_path, node, output):
        response, results = output
        if response != 0:
            self.emit('cancelled', None)
            logger.warning(f"Failed to start: {response}")
            return

        node_id, stream_info = results['streams'][0]
        stream_screen = Screen(*stream_info['size'])
        fd = self._get_fd()

        self.emit('ready', fd, node_id, stream_screen, self.is_selection_mode)
        logger.info("Ready for pipewire stream")

    def _new_session_path(self):
        self.session_counter += 1
        token = f'u{self.session_counter}'
        path = f'/org/freedesktop/portal/desktop/session/{self.sender_name}/{token}'
        return path, token

    def _new_request_path(self):
        self.request_counter += 1
        token = f'u{self.request_counter}'
        path = f'/org/freedesktop/portal/desktop/request/{self.sender_name}/{token}'
        return path, token

    def _get_fd(self):
        response, fd_list = self.proxy.call_with_unix_fd_list_sync(
            'OpenPipeWireRemote',
            GLib.Variant('(oa{sv})', (self.session_handle, {})),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None
        )
        return fd_list.get(0)

    def _screencast_call(self, method, callback, signature, *args, options={}):
        request_path, request_token = self._new_request_path()
        self.bus.signal_subscribe(
            'org.freedesktop.portal.Desktop',
            'org.freedesktop.portal.Request',
            'Response',
            request_path,
            None,
            Gio.DBusSignalFlags.NONE,
            callback
        )
        options['handle_token'] = GLib.Variant('s', request_token)

        try:
            method(signature, *args, options)
        except GLib.Error as error:
            self.emit('cancelled', error)
            logging.exception(error)

    def open(self, is_show_pointer, is_selection_mode):
        self.is_show_pointer = is_show_pointer
        self.is_selection_mode = is_selection_mode

        _, session_token = self._new_session_path()
        self._screencast_call(
            self.proxy.CreateSession,
            self._on_create_session_response,
            '(a{sv})',
            options={
                'session_handle_token': GLib.Variant('s', session_token),
            }
        )

    def close(self):
        session_proxy = Gio.DBusProxy.new_sync(
            self.bus,
            Gio.DBusProxyFlags.NONE,
            None,
            'org.freedesktop.portal.Desktop',
            self.session_handle,
            'org.freedesktop.portal.Session',
            None
        )
        session_proxy.Close()
        logger.info("Portal closed")
