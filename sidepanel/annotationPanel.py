import datetime

import gtk
import pango

from pychess.Utils.const import *
from pychess.System import conf
from pychess.System.glock import glock_connect
from pychess.System.prefix import addDataPrefix
from pychess.Utils.lutils import lmove

__title__ = _("Annotation")
__active__ = True
__icon__ = addDataPrefix("glade/panel_moves.svg")
__desc__ = _("Annotated game")


class Sidepanel(gtk.TextView):
    def __init__(self):
        gtk.TextView.__init__(self)
        
        self.set_editable(False)
        self.set_cursor_visible(False)
        self.set_wrap_mode(gtk.WRAP_WORD)

        self.cursor_standard = gtk.gdk.Cursor(gtk.gdk.LEFT_PTR)
        self.cursor_hand = gtk.gdk.Cursor(gtk.gdk.HAND2)
        
        self.textview = self
        
        self.nodeIters = []
        self.oldWidth = 0
        
        self.connect("motion-notify-event", self.motion_notify_event)
        self.connect("button-press-event", self.button_press_event)
        self.connect("expose-event", self.on_expose)
        
        self.textbuffer = self.get_buffer()
        
        self.textbuffer.create_tag("head1")
        self.textbuffer.create_tag("head2", weight=pango.WEIGHT_BOLD)
        self.textbuffer.create_tag("node", weight=pango.WEIGHT_BOLD)
        self.textbuffer.create_tag("comment", foreground="darkblue")
        self.textbuffer.create_tag("variation-toplevel")
        self.textbuffer.create_tag("variation-even", foreground="darkgreen", style="italic")
        self.textbuffer.create_tag("variation-uneven", foreground="darkred", style="italic")
        self.textbuffer.create_tag("selected", background_full_height=True, background="black", foreground="white")
        self.textbuffer.create_tag("margin", left_margin=4)
        self.textbuffer.create_tag("variation-margin", left_margin=20)

    def load (self, gmwidg):
        __widget__ = gtk.ScrolledWindow()
        __widget__.set_policy(gtk.POLICY_NEVER, gtk.POLICY_ALWAYS) #AUTOMATIC)
        __widget__.add(self.textview)

        self.boardview = gmwidg.board.view
        glock_connect(self.boardview.model, "game_changed", self.game_changed)
        glock_connect(self.boardview.model, "moves_undoing", self.moves_undoing)
        self.boardview.connect("shown_changed", self.shown_changed)

        self.gamemodel = gmwidg.board.view.model
        glock_connect(self.gamemodel, "game_loaded", self.game_loaded)

        # Connect to preferences
        
        def figuresInNotationCallback (none):
            self.update()
        conf.notify_add("figuresInNotation", figuresInNotationCallback)

        return __widget__

    def motion_notify_event(self, widget, event):
        if (event.is_hint):
            (x, y, state) = event.window.get_pointer()
        else:
            x = event.x
            y = event.y
            state = event.state
            
        if self.textview.get_window_type(event.window) != gtk.TEXT_WINDOW_TEXT:
            event.window.set_cursor(self.cursor_standard)
            return True
            
        (x, y) = self.textview.window_to_buffer_coords(gtk.TEXT_WINDOW_WIDGET, int(x), int(y))
        it = self.textview.get_iter_at_location(x, y)
        offset = it.get_offset()
        for ni in self.nodeIters:
            if offset >= ni["start"] and offset < ni["end"]:
                event.window.set_cursor(self.cursor_hand)
                return True
        event.window.set_cursor(self.cursor_standard)
        return True

    def button_press_event(self, widget, event):
        (wx, wy) = event.get_coords()
        
        (x, y) = self.textview.window_to_buffer_coords(gtk.TEXT_WINDOW_WIDGET, int(wx), int(wy))
        it = self.textview.get_iter_at_location(x, y)
        offset = it.get_offset()
        for ni in self.nodeIters:
            if offset >= ni["start"] and offset < ni["end"]:
                board = ni["node"]
                if board in self.gamemodel.boards:
                    self.boardview.shown = self.gamemodel.boards.index(board) + self.gamemodel.lowply
                else:
                    for vari in self.gamemodel.variations:
                        if board in vari:
                            # Go back to the common board of variations to let animation system work
                            board_in_vari = board
                            while board_in_vari not in self.gamemodel.boards:
                                board_in_vari = vari[board_in_vari.ply-self.gamemodel.lowply-1]
                            self.boardview.shown = board_in_vari.ply
                            break
                    self.gamemodel.boards = vari
                    self.boardview.shown = self.gamemodel.boards.index(board) + self.gamemodel.lowply

                self.update_selected_node()
                break
        return True

    # Update the selected node highlight
    def update_selected_node(self):
        self.textbuffer.remove_tag_by_name("selected", self.textbuffer.get_start_iter(), self.textbuffer.get_end_iter())
        start = None
        for ni in self.nodeIters:
            if ni["node"] == self.gamemodel.boards[self.boardview.shown - self.gamemodel.lowply]:
                start = self.textbuffer.get_iter_at_offset(ni["start"])
                end = self.textbuffer.get_iter_at_offset(ni["end"])
                self.textbuffer.apply_tag_by_name("selected", start, end)
                break

        if start:
            self.textview.scroll_to_iter(start, 0, use_align=False, yalign=0.1)

    # Recursively insert the node tree
    def insert_nodes(self, node, level=0, ply=0, result=None):
        buf = self.textbuffer
        end_iter = buf.get_end_iter # Convenience shortcut to the function
        new_line = False

        fan = conf.get("figuresInNotation", False)
        
        while (1): 
            start = end_iter().get_offset()
            
            if not node:
                break
            
            if not node.movestr:
                for comment in node.comments:
                    if node.ply == self.gamemodel.lowply:
                        self.insert_comment(comment + "\n", level)
                    else:
                        self.insert_comment(comment, level)
                node = node.next
                continue
            
            if ply > 0 and not new_line:
                buf.insert(end_iter(), " ")
            
            ply += 1

            movestr = node.movestr
            if fan:
                if node.color == BLACK:
                    movestr = lmove.san2WhiteFanRegex.sub(lmove.san2WhiteFanFunc, node.movestr)
                else:
                    movestr = lmove.san2BlackFanRegex.sub(lmove.san2BlackFanFunc, node.movestr)
            buf.insert(end_iter(), movestr + " ")
            
            startIter = buf.get_iter_at_offset(start)
            endIter = buf.get_iter_at_offset(end_iter().get_offset())
            
            if level == 0:
                buf.apply_tag_by_name("node", startIter, endIter)
            elif level == 1:
                buf.apply_tag_by_name("variation-toplevel", startIter, endIter)
            elif level % 2 == 0:
                buf.apply_tag_by_name("variation-even", startIter, endIter)
            else:
                buf.apply_tag_by_name("variation-uneven", startIter, endIter)

            buf.apply_tag_by_name("margin", startIter, endIter)

            if node == self.gamemodel.boards[self.boardview.shown - self.gamemodel.lowply]:
                buf.apply_tag_by_name("selected", startIter, endIter)
                
            ni = {}
            ni["node"] = node
            ni["start"] = startIter.get_offset()        
            ni["end"] = end_iter().get_offset()
            self.nodeIters.append(ni)
            
            # Comments
            for comment in node.comments:
                self.insert_comment(comment, level)

            new_line = False

            # Variations
            if level == 0 and len(node.variations):
                buf.insert(end_iter(), "\n")
                new_line = True
            
            for var in node.variations:
                if level == 0:
                    buf.insert_with_tags_by_name(end_iter(), "[", "variation-toplevel", "variation-margin")
                elif (level+1) % 2 == 0:
                    buf.insert_with_tags_by_name(end_iter(), " (", "variation-even", "variation-margin")
                else:
                    buf.insert_with_tags_by_name(end_iter(), " (", "variation-uneven", "variation-margin")
                
                self.insert_nodes(var[0], level+1, ply-1)

                if level == 0:
                    buf.insert(end_iter(), "]\n")
                elif (level+1) % 2 == 0:
                    buf.insert_with_tags_by_name(end_iter(), ") ", "variation-even", "variation-margin")
                else:
                    buf.insert_with_tags_by_name(end_iter(), ") ", "variation-uneven", "variation-margin")
            
            if node.next:
                node = node.next
            else:
                break

        if result and result != "*":
            buf.insert_with_tags_by_name(end_iter(), " "+result, "node")

    def insert_comment(self, comment, level=0):
        buf = self.textbuffer
        end_iter = buf.get_end_iter
        if level > 0:
            buf.insert_with_tags_by_name(end_iter(), comment, "comment", "margin")
        else:
            buf.insert_with_tags_by_name(end_iter(), comment, "comment")
        buf.insert(end_iter(), " ")

    def insert_header(self, gm):
        buf = self.textbuffer
        end_iter = buf.get_end_iter

        try:
            text = gm.tags['White']
        except:
            # pgn not processed yet
            return
        buf.insert_with_tags_by_name(end_iter(), text, "head2")
        white_elo = gm.tags['WhiteElo']
        if white_elo:
            buf.insert_with_tags_by_name(end_iter(), " %s" % white_elo, "head1")

        buf.insert_with_tags_by_name(end_iter(), " - ", "head1")

        text = gm.tags['Black']
        buf.insert_with_tags_by_name(end_iter(), text, "head2")
        black_elo = gm.tags['BlackElo']
        if black_elo:
            buf.insert_with_tags_by_name(end_iter(), " %s" % black_elo, "head1")
            
        result = ' ' + gm.tags['Result'] + '\n'
        buf.insert_with_tags_by_name(end_iter(), result, "head2")

        text = ""
        eco = gm.tags['ECO']
        if eco:
            text += eco

        event = gm.tags['Event']
        if event and event != "?":
            if len(text) > 0:
                text += ', '
            text += event

        site = gm.tags['Site']
        if site and site != "?":
            if len(text) > 0:
                text += ', '
            text += site

        round = gm.tags['Round']
        if round and round != "?":
            text += ', ' + _('round %s') % round

        game_date = gm.tags['Date']
        if game_date and not '?' in game_date:
            y, m, d = map(int, game_date.split('.'))
            # strftime() is limited to > 1900 dates
            try:
                text += ', ' + datetime.date(y, m, d).strftime('%x')
            except ValueError:
                text += ', ' + game_date
        elif game_date and not '?' in game_date[:4]:
            text += ', ' + game_date[:4]
        buf.insert_with_tags_by_name(end_iter(), text, "head1")

        buf.insert(end_iter(), "\n\n")

    def on_expose(self, widget, data):
        w = self.textview.get_allocation().width
        if not w == self.oldWidth:
            self.update()
            self.oldWidth = w
    
    # Update the entire notation tree
    def update(self):
        self.textbuffer.set_text('')
        self.nodeIters = []
        if self.boardview.shown >= self.gamemodel.lowply:
            self.insert_header(self.gamemodel)
            self.insert_nodes(self.gamemodel.boards[0], result=reprResult[self.gamemodel.status])

    def game_loaded(self, model, uri):
        self.update()
            
    def shown_changed (self, board, shown):
        self.update_selected_node()

    def moves_undoing(self, game, moves):
        assert game.ply > 0, "Can't undo when ply <= 0"
        start = self.textbuffer.get_start_iter()
        end = self.textbuffer.get_end_iter()
        for ni in reversed(self.nodeIters):
            if ni["node"] == self.gamemodel.boards[-2]:
                start = self.textbuffer.get_iter_at_offset(ni["start"])
                break
        self.textbuffer.delete(start, end)
        

    def game_changed (self, game):
        node = game.getBoardAtPly(game.ply)
        buf = self.textbuffer
        end_iter = buf.get_end_iter
        start = end_iter().get_offset()

        buf.insert(end_iter(), node.movestr + " ")
        startIter = buf.get_iter_at_offset(start)
        endIter = buf.get_iter_at_offset(end_iter().get_offset())
        buf.apply_tag_by_name("node", startIter, endIter)

        ni = {}
        ni["node"] = node
        ni["start"] = startIter.get_offset()        
        ni["end"] = end_iter().get_offset()
        self.nodeIters.append(ni)
        self.update_selected_node()
