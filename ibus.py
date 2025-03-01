#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# UniEmoji: ibus engine for unicode emoji and symbols by name
#
# Copyright (c) 2013, 2015 Lalo Martins <lalo.martins@gmail.com>
#
# based on https://github.com/ibus/ibus-tmpl/
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.

import gi
gi.require_version('IBus', '1.0')
from gi.repository import IBus
from gi.repository import GLib
from gi.repository import GObject

import os
import sys
import getopt
import locale

from uniemoji import UniEmoji

__base_dir__ = os.path.dirname(__file__)

debug_on = True
def debug(*a, **kw):
    if debug_on:
        print(*a, **kw)

# gee thank you IBus :-)
num_keys = []
for n in range(1, 10):
    num_keys.append(getattr(IBus, str(n)))
num_keys.append(getattr(IBus, '0'))
del n

numpad_keys = []
for n in range(1, 10):
    numpad_keys.append(getattr(IBus, 'KP_' + str(n)))
numpad_keys.append(getattr(IBus, 'KP_0'))
del n

###########################################################################
# the engine
class UniEmojiIBusEngine(IBus.Engine):
    __gtype_name__ = 'UniEmojiIBusEngine'

    def __init__(self):
        super(UniEmojiIBusEngine, self).__init__()
        self.uniemoji = UniEmoji()
        global debug_on
        debug_on = self.uniemoji.settings.get('debug', False)
        self.is_invalidate = False
        self.preedit_string = ''
        self.lookup_table = IBus.LookupTable.new(10, 0, True, True)
        self.prop_list = IBus.PropList()
        self._setup_prefixes(list(self.uniemoji.get_prefixes()))
        
        debug("Create UniEmoji engine OK")

    def _setup_prefixes(self, prefixes):
        self.prefixes = prefixes
        self.lastnchars = ""
        self.max_prefix_len = max(len(p) for p in prefixes) if len(prefixes) > 0 else 0
        self.active_prefixes = []
        self.max_active_prefix_len = 0
        debug(self.prefixes)
        
    def _reset_active_prefixes(self):
        self.active_prefixes.clear()
        self.max_active_prefix_len = 0
        self.lastnchars = ""
        
    def _add_active_prefix(self, prefix):
        if prefix not in self.active_prefixes:
            self.active_prefixes.append(prefix)
            self.max_active_prefix_len = max(self.max_active_prefix_len, len(prefix))
            debug('prefix "{}" activated'.format(prefix))
            
    def _remove_active_prefix(self, index):
        del self.active_prefixes[index]
        self.max_active_prefix_len = max(len(p) for p in self.active_prefixes)
        debug('prefix removed')
        
    def set_lookup_table_cursor_pos_in_current_page(self, index):
        '''Sets the cursor in the lookup table to index in the current page

        Returns True if successful, False if not.
        '''
        page_size = self.lookup_table.get_page_size()
        if index > page_size:
            return False
        page, pos_in_page = divmod(self.lookup_table.get_cursor_pos(),
                                   page_size)
        new_pos = page * page_size + index
        if new_pos > self.lookup_table.get_number_of_candidates():
            return False
        self.lookup_table.set_cursor_pos(new_pos)
        return True

    def do_candidate_clicked(self, index, dummy_button, dummy_state):
        if self.set_lookup_table_cursor_pos_in_current_page(index):
            self.commit_candidate()

    def do_process_key_event(self, keyval, keycode, state):
        # debug("process_key_event(%04x, %04x, %04x)" % (keyval, keycode, state))
        # debug(IBus.keyval_name(keyval))

        # ignore key release events
        is_press = ((state & IBus.ModifierType.RELEASE_MASK) == 0)
        if not is_press:
            return False
        if state & (IBus.ModifierType.CONTROL_MASK | IBus.ModifierType.MOD1_MASK | IBus.ModifierType.MOD2_MASK) != 0:
            self.commit_string(self.preedit_string)
            return False

        if len(self.prefixes) > 0:
            # TODO: Handle Return and Enter correctly
            # Add the key to the lastnchars buffer
            if keyval in (IBus.Escape,):
                # debug('escape')
                self.lastnchars = ""
                self.commit_string(self.preedit_string)
                return False
            elif keyval in (IBus.BackSpace,):
                # debug('backspace')
                if len(self.active_prefixes) == 0:
                    self.lastnchars = self.lastnchars[:-1]
                    if len(self.preedit_string) > 0:
                        self.preedit_string = self.preedit_string[:-1]
                        self.update_prefix_text()
                        return True
                    else:
                        return False
                else:
                    self.lastnchars = self.lastnchars[:-1]
                    self.preedit_string = self.preedit_string[:-1]
                    for i in range(len(self.active_prefixes)):
                        if self.active_prefixes[i] not in self.preedit_string:
                            self._remove_active_prefix(i)
                    # self.update_candidates()
                    self.is_invalidate = True
                    self.update_prefix_text()
                    return True
            elif keyval < 128 and chr(keyval).isprintable():
                self.lastnchars += chr(keyval)
                if len(self.lastnchars) > self.max_prefix_len:
                    self.lastnchars = self.lastnchars[-self.max_prefix_len:]
                debug('lastnchars:', self.lastnchars)
                    
                partial_match = False
                for prefix in self.prefixes:
                    # Check for a partial match of the first characters of the prefix in the last characters of lastnchars
                    for i in range(1, len(prefix) + 1):
                        if prefix.startswith(self.lastnchars[-i:]):                        
                            partial_match = True
                            if prefix in self.lastnchars:
                                self._add_active_prefix(prefix)
                            break
                del prefix
                
                if len(self.active_prefixes) == 0:
                    if partial_match:
                        self.preedit_string += chr(keyval)
                        self.is_invalidate = True
                        self.update_prefix_text()
                        return True
                    else:
                        self.commit_string(self.preedit_string + chr(keyval))
                        return True
                    
        
        if self.preedit_string:
            if keyval in (IBus.Return, IBus.KP_Enter):
                if self.lookup_table.get_number_of_candidates() > 0:
                    self.commit_candidate()
                    return True
                else:
                    self.commit_string(self.preedit_string)
                    return False
            elif keyval == IBus.Escape:
                if len(self.prefixes) == 0:
                    self.preedit_string = ''
                    self.update_candidates()
                    return True
                else:
                    self.commit_string(self.preedit_string)
                    return False
            elif keyval == IBus.BackSpace:
                self.preedit_string = self.preedit_string[:-1]
                self.invalidate()
                return True
            elif keyval in num_keys:
                index = num_keys.index(keyval)
                if self.set_lookup_table_cursor_pos_in_current_page(index):
                    self.commit_candidate()
                    return True
                return False
            elif keyval in numpad_keys:
                index = numpad_keys.index(keyval)
                if self.set_lookup_table_cursor_pos_in_current_page(index):
                    self.commit_candidate()
                    return True
                return False
            elif keyval in (IBus.Page_Up, IBus.KP_Page_Up, IBus.Left, IBus.KP_Left):
                self.page_up()
                return True
            elif keyval in (IBus.Page_Down, IBus.KP_Page_Down, IBus.Right, IBus.KP_Right):
                self.page_down()
                return True
            elif keyval in (IBus.Up, IBus.KP_Up):
                self.cursor_up()
                return True
            elif keyval in (IBus.Down, IBus.KP_Down):
                self.cursor_down()
                return True
            
        if keyval == IBus.space:
            if len(self.candidates) == 0 and len(self.preedit_string) != 0:
                self.commit_string(self.preedit_string + chr(keyval))
                return True
            if len(self.preedit_string) == 0:
                # Insert space if that's all you typed (so you can more easily
                # type a bunch of emoji separated by spaces)
                return False

        # Allow typing all ASCII letters and punctuation, except digits
        if ord(' ') <= keyval < ord('0') or \
           ord('9') < keyval <= ord('~'):
            if state & (IBus.ModifierType.CONTROL_MASK | IBus.ModifierType.MOD1_MASK) == 0:
                self.preedit_string += chr(keyval)
                self.invalidate()
                return True
        else:
            if keyval < 128 and self.preedit_string:
                self.commit_string(self.preedit_string)

        return False

    def invalidate(self):
        if self.is_invalidate:
            return
        self.is_invalidate = True
        GLib.idle_add(self.update_candidates)


    def page_up(self):
        if self.lookup_table.page_up():
            self._update_lookup_table()
            return True
        return False

    def page_down(self):
        if self.lookup_table.page_down():
            self._update_lookup_table()
            return True
        return False

    def cursor_up(self):
        if self.lookup_table.cursor_up():
            self._update_lookup_table()
            return True
        return False

    def cursor_down(self):
        if self.lookup_table.cursor_down():
            self._update_lookup_table()
            return True
        return False

    def commit_string(self, text, update_candidates=True):
        self.commit_text(IBus.Text.new_from_string(text))
        self.preedit_string = ''
        if update_candidates:
            self.update_candidates()
        self._reset_active_prefixes()

    def commit_candidate(self):
        self.commit_string(self.candidates[self.lookup_table.get_cursor_pos()])

    def update_candidates(self):
        debug('preedit_string:', self.preedit_string)
        
        preedit_len = len(self.preedit_string)
        attrs = IBus.AttrList()
        self.lookup_table.clear()
        self.candidates = []

        if preedit_len > 0:
            # if (len(self.prefixes) > 0):
            #     queries = []
            #     for p in self.active_prefixes:
            #         if self.preedit_string.startswith(p):
            #             query = self.preedit_string[len(p):]
            #             if query not in queries:
            #                 queries.append(query)
                    
            #     uniemoji_results = []
            #     for query in queries:
            #         uniemoji_results = self.uniemoji.find_characters(query)
            # else:
            if len(self.active_prefixes) > 0:
                # TODO Here too, we only consider the first prefix
                uniemoji_results = self.uniemoji.find_characters(self.preedit_string[len(self.active_prefixes[0]):], self.active_prefixes)
            else:
                uniemoji_results = self.uniemoji.find_characters(self.preedit_string, self.active_prefixes)
            for char_sequence, display_str in uniemoji_results:
                candidate = IBus.Text.new_from_string(display_str)
                self.candidates.append(char_sequence)
                self.lookup_table.append_candidate(candidate)

        text = IBus.Text.new_from_string(self.preedit_string)
        text.set_attributes(attrs)
        self.update_auxiliary_text(text, preedit_len > 0)

        attrs.append(IBus.Attribute.new(IBus.AttrType.UNDERLINE,
                IBus.AttrUnderline.SINGLE, 0, preedit_len))
        text = IBus.Text.new_from_string(self.preedit_string)
        text.set_attributes(attrs)
        self.update_preedit_text(text, preedit_len, preedit_len > 0)
        self._update_lookup_table()
        self.is_invalidate = False
        
        if (len(self.candidates) == 1 and self.uniemoji.settings.get('commit_on_single_candidate', True)):
            self.commit_candidate()
        elif len(self.candidates) == 0 and self.uniemoji.settings.get('commit_on_zero_candidates', True) and len(self.preedit_string) > self.max_active_prefix_len:
            self.commit_string(self.preedit_string, False)
        
    def update_prefix_text(self):
        preedit_len = len(self.preedit_string)
        attrs = IBus.AttrList()
        
        text = IBus.Text.new_from_string(self.preedit_string)
        text.set_attributes(attrs)
        self.update_auxiliary_text(text, preedit_len > 0)

        attrs.append(IBus.Attribute.new(IBus.AttrType.UNDERLINE,
                IBus.AttrUnderline.SINGLE, 0, preedit_len))
        text = IBus.Text.new_from_string(self.preedit_string)
        text.set_attributes(attrs)
        self.update_preedit_text(text, preedit_len, preedit_len > 0)
        self.is_invalidate = False

    def _update_lookup_table(self):
        visible = self.lookup_table.get_number_of_candidates() > 0
        self.update_lookup_table(self.lookup_table, visible)

    def do_focus_in(self):
        debug("focus_in")
        self.register_properties(self.prop_list)

    def do_focus_out(self):
        debug("focus_out")
        self.do_reset()

    def do_reset(self):
        debug("reset")
        self.preedit_string = ''

    def do_property_activate(self, prop_name):
        debug("PropertyActivate(%s)" % prop_name)

    def do_page_up(self):
        return self.page_up()

    def do_page_down(self):
        return self.page_down()

    def do_cursor_up(self):
        return self.cursor_up()

    def do_cursor_down(self):
        return self.cursor_down()

###########################################################################
# the app (main interface to ibus)
class IMApp:
    def __init__(self, exec_by_ibus):
        if not exec_by_ibus:
            global debug_on
            debug_on = True
        self.mainloop = GLib.MainLoop()
        self.bus = IBus.Bus()
        self.bus.connect("disconnected", self.bus_disconnected_cb)
        self.factory = IBus.Factory.new(self.bus.get_connection())
        self.factory.add_engine("uniemoji", GObject.type_from_name("UniEmojiIBusEngine"))
        if exec_by_ibus:
            self.bus.request_name("org.freedesktop.IBus.UniEmoji", 0)
        else:
            xml_path = os.path.join(__base_dir__, 'uniemoji.xml')
            if os.path.exists(xml_path):
                component = IBus.Component.new_from_file(xml_path)
            else:
                xml_path = os.path.join(os.path.dirname(__base_dir__),
                                        'ibus', 'component', 'uniemoji.xml')
                component = IBus.Component.new_from_file(xml_path)
            self.bus.register_component(component)

    def run(self):
        self.mainloop.run()

    def bus_disconnected_cb(self, bus):
        self.mainloop.quit()


def launch_engine(exec_by_ibus):
    IBus.init()
    IMApp(exec_by_ibus).run()

def print_help(out, v = 0):
    print("-i, --ibus             executed by IBus.", file=out)
    print("-h, --help             show this message.", file=out)
    print("-d, --daemonize        daemonize ibus", file=out)
    sys.exit(v)

def main():
    try:
        locale.setlocale(locale.LC_ALL, "")
    except:
        pass

    exec_by_ibus = False
    daemonize = False

    shortopt = "ihd"
    longopt = ["ibus", "help", "daemonize"]

    try:
        opts, args = getopt.getopt(sys.argv[1:], shortopt, longopt)
    except getopt.GetoptError:
        print_help(sys.stderr, 1)

    for o, a in opts:
        if o in ("-h", "--help"):
            print_help(sys.stdout)
        elif o in ("-d", "--daemonize"):
            daemonize = True
        elif o in ("-i", "--ibus"):
            exec_by_ibus = True
        else:
            print("Unknown argument: %s" % o, file=sys.stderr)
            print_help(sys.stderr, 1)

    if daemonize:
        if os.fork():
            sys.exit()

    launch_engine(exec_by_ibus)

if __name__ == "__main__":
    main()
