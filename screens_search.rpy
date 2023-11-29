## Search screen ##############################################################
##
## Search through text you've already read

# @TODO: Split text with a visual separator if there's an "if/jump"
# @TODO: InitializeSearchEntries/CreateSearchEntry can probably be optimized further. The "x in y" string checks eat some cycles

init -10 python:
    import re
    from operator import itemgetter
    from collections import OrderedDict
    
    chr_choice = CharacterData("Choice", "", category='special')
    chr_title  = CharacterData("Title", "", category='special')
    chr_tip    = CharacterData("Tip", "", category='special')
    who_choice = NVLCharacter2(chr_choice, is_speaker=False, what_color="#F88")
    who_title  = NVLCharacter2(chr_title, is_speaker=False, what_color="#FFF")

    def SearchTitle(text):
        ## Adds a search title that otherwise isn't displayed in-game
        pass

    def SearchText(speaker, text):
        ## Adds a search entry that otherwise isn't displayed in-game
        pass

    class SearchEntry(python_object):
        def __init__(self, node, who=None, what="", tip_name=None, entry_type="msg", global_index=None):
            self.node = node
            self.label = node.name
            if global_index:
                self.global_index = global_index
            else:
                self.global_index = GetGlobalIndexFromNode(self.node)
            self.search_index = -1
            self.chapter = -1
            self.who = who
            self.what = what
            self.type = entry_type
            self.tip_name = tip_name
            
            self.Update()
        
        def Update(self):
            if self.type == 'choice':
                ## Update the what field in case the user updated their selection
                temp = python_list()
                for item in self.node.items:
                    chosen = renpy.game.persistent._chosen.get((self.label, item[0]), False)
                    if chosen:
                        temp.append("{color=#fc8}    "+item[0]+"{/color}")
                    else:
                        temp.append("{color=#f88}    "+item[0]+"{/color}")
                self.what = '\n'.join(temp)
    
    class Search(python_object):
        def __init__(self):
            self.processed_labels = python_dict()
            self.all_entries = OrderedDict()
            self.seen_entries_all = python_list()
            self.prev_tiporb = None
            
            self.len_entries = -1
            self.search_text = None
            self.vbox_top_idx = 0
            self.context_length = 17 #Number of lines to show above and below search result
            self.vbox_spacing = 0
            self.found_idxs = None
            self.found_titles = python_list()
            self.error = ""
            self.start_node = renpy.game.script.lookup("start")
            self.end_node = renpy.game.script.lookup("the_end")
            self.start_node_tips = renpy.game.script.lookup("tip_example1")
            self.end_node_tips = renpy.game.script.lookup("tip_end")
            
            self.hide_menus = [SetScreenVariable("filter_visible", False), SetScreenVariable("menu_visible", False)]
            
            self.vbox = None
            self.view = None
            self.input = Input2(
                style="search_input",
                caret_ysize=20,
                max_chars=100,
                copypaste=True,
                changed=self.InputChanged,
                enter_callback=self.Next,
                highlight_color=gui.highlight_color)
            
            self.chapter = 0
            self.current_idxs = python_list()
            self.chapter_labels = ["start", "chapter2", "chapter3", "chapter4", "chapter5", "tip_example1"]
            self.chapter_global_idxs = python_list()
            self.scene_titles = python_list()
            self.note_unlocks = python_list()
            self.speaker_enabled = python_list()
            self.seen_entries_by_chapter = python_list()
            self.entry_buffer = python_dict()
            for label in self.chapter_labels:
                node = renpy.game.script.lookup(label)
                self.chapter_global_idxs.append(GetGlobalIndexFromNode(node))
                self.speaker_enabled.append(python_dict())
                self.seen_entries_by_chapter.append(python_list())
                self.current_idxs.append(1)
            
            self.InitializeSearchEntries()
            self.UpdateMessages(update_gui=False)
            
             
        @property
        def current_idx(self):
            rv = self.current_idxs[self.chapter]
            if rv >= len(self.seen_entries_by_chapter[self.chapter]):
                rv = len(self.seen_entries_by_chapter[self.chapter])-1

            if rv < 0:
                return 0
                #raise Exception("Search: Current chapter has no seen entries")

            return self.current_idxs[self.chapter]

        @current_idx.setter
        def current_idx(self, val):
            val = max(1, min(self.max_top_idx, val))
            self.current_idxs[self.chapter] = val
        
        @property
        def line_count(self):
            return len(self.seen_entries_by_chapter[self.chapter])
        
        @property
        def max_top_idx(self):
            return self.line_count-1

        @property
        def is_all_speakers_enabled(self):
            for speaker, val in self.speaker_enabled[self.chapter].items():
                if val[0]==False:
                    return False
            return True

        def Clear(self):
            self.entry_buffer.clear()
        
        def ClearResults(self):
            self.found_idxs = None
        

        def SetChapter(self):
            self.ClearResults()
            if self.vbox:
                self.vbox.children = python_list()
            
            self.entry_buffer.clear()
            w_notif = renpy.get_widget(None, "search_notification")
            w_lines = renpy.get_widget(None, "search_lines")
            w_notif.set_text("")
            w_lines.set_text("")
                
            self.Populate()


        def Scroll(self, increment=None, line=None):
            if increment is None and line is None:
                raise Exception("Either increment or line must have a value")
            
            if len(self.seen_entries_by_chapter[self.chapter])==0:
                return
            
            self.current_idx += increment
            
            ## Scroll past titles
            if self.seen_entries_by_chapter[self.chapter][self.current_idx].type == 'title':
                self.current_idx += increment
            
            self.Populate()
            
            ## Hide any open menus
            for i in self.hide_menus:
                i()
            
            ## Process focus-able widgets so hover effects will still take effect
            for i, _, _ in self.entry_buffer.values():
                i.per_interact()
        
        
        def ExitMenu(self):
            self.Clear()
            if persistent.search_clear_initial:
                self.search_text = None
                self.input.clear()
                self.InputChanged()
                
                self.ClearResults()
        
        
        def EnableAllSpeakers(self, val=True):
            x = self.speaker_enabled[self.chapter]
            for key in x:
                x[key][0] = val
            self.InputChanged()
        
        
        def Copy(self, node):
            entry = self.CreateSearchEntry(GetGlobalIndexFromNode(node))
            text_raw = entry.what
            text_raw = text_raw.replace('    ', '')
            if "{time" in text_raw:
                txt_temp = renpy.text.text.Text(text_raw)
                txt_temp.update()
                text_raw = "".join([x[1] for x in txt_temp.tokens])
            #text_clean = renpy.filter_text_tags(text_raw, allow=gui.history_allow_tags)
            try:
                clipboard.copy(text_raw, text_raw) #, text_raw)
            except:
                pass
        
        
        def InputChanged(self, txt=-1):
            if txt != -1:
                self.search_text = txt
            self.ClearResults()
        
        
        def Next(self):
            self.FindText(1)
        
        
        def Previous(self):
            self.FindText(-1)
        
        def IsMatch(self, src, target):
            msg = src if persistent.search_case_sensitive else src.lower()
            
            # Process {time} tags
            if "{time" in msg:
                txt_temp = renpy.text.text.Text(msg)
                txt_temp.update()
                msg = "".join([x[1] for x in txt_temp.tokens])
            
            if persistent.search_exact_match:
                if target in msg:
                    found = True
                else:
                    found = False
            else:
                found = True
                for t in target:
                    if t not in msg:
                        found = False
                        break
            return found
        
        def FindText(self, direction=1):
            w_notif = renpy.get_widget(None, "search_notification")
            w_lines = renpy.get_widget(None, "search_lines")
            self.input.addToHistory() ## Save the search to history
            w_notif.set_text("")
            
            if self.search_text is None:
                self.search_text = ""
            
            ## Find text in all messages
            reused_results = True
            if self.found_idxs is None:
                self.found_idxs = OrderedDict() # found_idxs[index] = Is this a message (True) or scene title (False)
                self.entry_buffer.clear() #Clear saved entries so we can highlight them correctly
                reused_results = False
                
                if persistent.search_case_sensitive:
                    target = self.search_text
                else:
                    target = self.search_text.lower()
                    
                if not persistent.search_exact_match:
                    target = target.split(" ")
                    
                prev_who = None
                for i in range(self.line_count):
                    m = self.seen_entries_by_chapter[self.chapter][i]
                    if type(m.who)==NVLCharacter2 and m.who.data:
                        who = m.who.data
                        prev_who = who
                    else:
                        raise Exception("'Who' not found: {}".format(m.who))
                    
                    if self.speaker_enabled[self.chapter][who.name][0]:
                        if self.IsMatch(m.what, target):
                            self.found_idxs[i] = True
                    
                    ## Check if text is in tip names
                    if (chr_tip.name in self.speaker_enabled[self.chapter]) and (self.speaker_enabled[self.chapter][chr_tip.name][0]):
                        if m.tip_name and persistent.tip_visibility[m.tip_name]==2:
                            msg = "Tip: " + tip_list[m.tip_name]
                            if self.IsMatch(msg, target):
                                self.found_idxs[i] = True
                
                ## Check if text is in scene name
                ## Seems to already be covered by earlier code
                """
                if self.speaker_enabled[self.chapter][chr_title.name][0]:
                    for s in self.scene_titles:
                        if self.IsMatch(s.what, target):
                            for i, m in enumerate(self.seen_entries_by_chapter[self.chapter]):
                                if m.search_index > s.search_index:
                                    self.found_idxs[i] = False
                                    break
                    
                    self.found_idxs = OrderedDict(sorted(self.found_idxs.items()))
                """
            
            if (len(self.found_idxs) == 0):
                w_lines.set_text("Not found")
                return
            
            ## Change index to next message 
            success = False
            found_idx = None
            if direction > 0:
                for i, msg_idx in enumerate(self.found_idxs):
                    if not reused_results and msg_idx==self.current_idx:
                        ## Edge case when the first message has the text and we only started scanning now
                        found_idx = i+1
                        success = True
                        break
                    elif msg_idx > self.current_idx and self.current_idx < self.max_top_idx:
                        self.current_idx = msg_idx
                        found_idx = i+1
                        success = True
                        break
                        
                if not success:
                    self.current_idx = python_list(self.found_idxs.keys())[0]
                    found_idx = 1
                    w_notif.set_text("End of document.")
            
            else:
                for i, msg_idx in reversed(python_list(enumerate(self.found_idxs))):
                    if msg_idx < self.current_idx:
                        self.current_idx = msg_idx
                        found_idx = i+1
                        success = True
                        break
                        
                if not success:
                    self.current_idx = python_list(self.found_idxs.keys())[-1]
                    found_idx = len(self.found_idxs)
                    w_notif.set_text("End of document.")
            
            self.Populate()
            
            w_lines.set_text("Match {:d}/{:d}\nLine {:d}/{:d}".format(
                    found_idx,
                    len(self.found_idxs),
                    self.current_idx+1,
                    self.line_count
                    ))
        
        
        def Populate(self, upper_limit=None, highlight_idx=None):
            self.vbox = renpy.get_widget(None, "search_view_vbox")
            self.view = renpy.get_widget(None, "search_view")
            view_title = renpy.get_widget(None, "search_view_title")
            view_bar = renpy.get_widget(None, "search_view_bar")
            self.vbox._clear()
            
            self.lower_limit = max(0, min(self.current_idx, self.max_top_idx))
            if upper_limit:
                self.upper_limit = min(upper_limit, self.line_count)
            else:
                self.upper_limit = min(self.current_idx+self.context_length, self.line_count)
            
            for i in range(self.lower_limit, self.upper_limit):
                if i==self.lower_limit:
                    ## Get this scene's title
                    title_idx = i
                    
                    if self.seen_entries_by_chapter[self.chapter][i].type != 'title':
                        for s in self.scene_titles:
                            if s.chapter != self.chapter:
                                continue
                            
                            if self.lower_limit >= s.search_index:
                                title_idx = s.search_index
                            else:
                                break
                    
                    title_widget = self.CreateDisplayableEntry(title_idx)
                    if hasattr(title_widget.child, 'text'):
                        view_title.set_text(title_widget.child.text[0])
                    else:
                        view_title.set_text("<Title not found>")
                    
                    if title_idx == i:
                        continue
                
                widget = self.CreateDisplayableEntry(i, highlight=(highlight_idx==i))
                self.vbox.add(widget)
                
            view_bar.per_interact()
        
        
        def CreateDisplayableEntry(self, idx, highlight=False):
            if (not highlight) and (idx in self.entry_buffer):
                ## Reuse pre-computed entries for performance
                ## Put this entry at the top of the buffer so it doesn't cycle out
                return self.entry_buffer[idx][0]
            
            m = self.seen_entries_by_chapter[self.chapter][idx]
            if m.type=='choice':
                m.Update()
            
            msg = m.what
            msg = msg.replace('%%', '%')
            
            found = False
            if self.found_idxs and (idx in self.found_idxs) and self.found_idxs[idx]==True:
                found = True
                
                ## create the "what" with highlighted text
                if self.search_text == "" or self.search_text == " " or self.search_text is None:
                    what = msg
                else:
                    if "{time" in msg:
                        txt_temp = renpy.text.text.Text(msg)
                        txt_temp.update()
                        msg = "".join([x[1] for x in txt_temp.tokens])
                
                    if persistent.search_case_sensitive:
                        source = msg
                        target = self.search_text
                    else:
                        source = msg.lower()
                        target = self.search_text.lower()
                        
                    if persistent.search_exact_match:
                        split_idxs = [source.find(target), source.find(target)+len(target)]
                    else:
                        split_idxs = python_list()
                        end_idxs = python_list()
                        target = target.split(" ")
                        
                        for t in target:
                            split_idxs.append(source.find(t))
                            split_idxs.append(split_idxs[-1]+len(t))
                        split_idxs.sort()
                    
                    ## Put the highlight tags around the located sections
                    what_split = [msg[i:j] for i,j in zip(split_idxs, split_idxs[1:]+[None])]
                    what = msg[:split_idxs[0]]
                    for i in range(int(len(split_idxs)//2)):
                        if i>0:
                            what += msg[split_idxs[i*2-1]:split_idxs[i*2]]
                        what += "{u}{color=#f88}{outlinecolor=#000}" + msg[split_idxs[2*i]:split_idxs[2*i+1]] + "{/outlinecolor}{/color}{/u}"
                    what += msg[split_idxs[-1]:]
            else:
                what = msg
            
            if m.type=='title':
                label_args = python_dict()
                label_args["label"] = what
                label_args["style"] = "search_scene"
                b = renpy.ui._label(**label_args)
            
            else:
                # Who
                who_args = python_dict()
                who_args["label"] = ""
                who_args["style"] = "search_name"
                who_args["text_style"] = "search_name_text"
                
                if type(m.who)==NVLCharacter2 and m.who.data and m.who.data.indicator():
                    who_args["label"] = m.who.data.indicator()
                    if gui.preference("colored_speaker"):
                        who_args["text_color"] = m.who.data.color
                        
                    
                    if gui.preference("speaker_indicator") == "circle":
                        if hasattr(m.who, 'what_args') and "size" in m.who.what_args:
                            text_size = m.who.what_args["size"]
                        else:
                            text_size = gui.text_size
                        who_args["text_size"] = 52
                        who_args["ysize"] = 24
                        who_args["top_margin"] = int(0.4*text_size-32)
                        who_args["xoffset"] = 3
                    else:
                        if hasattr(m.who, 'what_args') and "size" in m.who.what_args:
                            who_args["text_size"] = m.who.what_args["size"]
                        
                    if hasattr(m.who, 'what_args') and "outlines" in m.who.what_args:
                        who_args["text_outlines"] = m.who.what_args["outlines"]
                    elif not hasattr(m.who, 'what_args') or "outlines" not in m.who.what_args:
                        who_args["text_outlines"] = gui.dialogue_outline[gui.preference("dialogue_outline_idx")]
                        
                #w_who = renpy.ui._label(**who_args)
                w_who = ConstantLabel(**who_args)
                
                
                # What
                if hasattr(m.who, 'what_args'):
                    what_args = m.who.what_args.copy()
                else:
                    what_args = python_dict()
                what_args["style"] = "search_what_text"
                
                if type(m.who)==NVLCharacter2:
                    if hasattr(m.who, 'what_args') and "color" in m.who.what_args:
                        what_args["color"] = m.who.what_args["color"]
                    elif gui.preference("colored_text") and m.who.data.color:
                        what_args["color"] = m.who.data.color
                    
                    if not hasattr(m.who, 'what_args') or "outlines" not in m.who.what_args:
                        what_args["outlines"] = gui.dialogue_outline[gui.preference("dialogue_outline_idx")]
                    
                    w_what = ConstantText(m.who.what_prefix + what + m.who.what_suffix, **what_args)
                else:
                    w_what = ConstantText(what, **what_args)
                
                ## Get note entry
                note_entry = (1,1)
                for n in self.note_unlocks:
                    if m.global_index > n.global_index:
                        note_entry = n
                    else:
                        break
                
                # Final entry
                h = renpy.display.layout.MultiBox(layout="fixed", style="hbox")
                h.add(w_who)
                h.add(w_what)
                    
                if m.tip_name and persistent.tip_visibility[m.tip_name]==2:
                    tip_args = python_dict()
                    tip_args["label"] = "Tip: " + tip_list[m.tip_name]
                    tip_args["style"] = "search_tip"
                    b2 = renpy.ui._label(**tip_args)
                    
                    ## Put the tip and text one after the other
                    h2 = renpy.display.layout.MultiBox(layout="fixed", style="vbox")
                    h2.add(b2)
                    h2.add(h)
                    h = h2
                
                if highlight:
                    b = renpy.display.behavior.Button(h, style="search_button_current")
                elif found:
                    b = renpy.display.behavior.Button(h, style="search_button{}_found".format(idx%2))
                else:
                    b = renpy.display.behavior.Button(h, style="search_button{}".format(idx%2))
                
                b.action = self.hide_menus+[
                    SetScreenVariableCallback("menu_position", Function(MenuClickAction,3)),
                    SetScreenVariable("menu_visible", True),
                    SetScreenVariable("clicked_node", m.node),
                    SetScreenVariable("clicked_note_entry", note_entry),
                    ]
            
            # Store the entry and clear out the oldest in the buffer
            self.entry_buffer[idx] = (b, highlight, time.time())
            if len(self.entry_buffer)>20:
                oldest_time = time.time()
                oldest_idx = -1
                for idx, (_, e_highlighted, e_time) in self.entry_buffer.items():
                    if not e_highlighted and e_time < oldest_time:
                        oldest_time = e_time
                        oldest_idx = idx
                    
                del self.entry_buffer[oldest_idx]
            
            return b
        
        
        def CreateSearchEntry(self, global_index):
            node = GetNodeFromGlobalIndex(global_index)
            if node is None:
                raise Exception("Script was likely changed. Delete script.rpyc then persistent data.")
            
            rv = None
            
            if type(node)==renpy.ast.Say:
                rv = SearchEntry(node, global_index=global_index)
                
                if "{tip" in node.what:
                    rv.tip_name = re.search("{tip=(.*?)}", node.what).group(1)
                elif self.prev_tiporb:
                    rv.tip_name = self.prev_tiporb
                    self.prev_tiporb = None
                
                ## Strip unneeded text tags (anything that's not a time tag)
                rv.what = re.sub("({(?!time).*?})", "", node.what)
                rv.who = renpy.ast.eval_who(node.who, node.who_fast)
            
            elif type(node)==renpy.ast.Python:
                if "SceneTitle" in node.code.source:
                    scene_name = node.code.source[len("SceneTitle(\""):-2]

                    ## Only add the first instance of a title. There are multiple instances of titles for bad end handling
                    found = False
                    for temp in self.scene_titles:
                        if temp.what == scene_name:
                            found = True
                            break

                    if not found:
                        rv = SearchEntry(node, entry_type="title", what=scene_name, who=who_title, global_index=global_index)
                        self.scene_titles.append(rv)
                
                elif "UnlockNote" in node.code.source:
                    temp = node.code.source[len("UnlockNote("):-1].replace('"', '').split(", ")
                    chapter  = int(temp[0][1])
                    note_num = int(temp[0][3:])
                    
                    if len(temp)==1 or int(temp[1])==1:
                        self.note_unlocks.append(SearchEntry(node, entry_type="note", what=(chapter, note_num), global_index=global_index))
                
                elif "TipOrbShow" in node.code.source:
                    self.prev_tiporb = re.search('TipOrbShow\("(.*?)"\)', node.code.source).group(1)
                    if self.prev_tiporb in ["example1", "example2"]:
                        self.prev_tiporb = None
                
                elif "SearchText" in node.code.source:
                    result = re.search('SearchText\((.*?),[ ]*"(.*?)"\)', node.code.source)
                    speaker = result.group(1).strip()
                    
                    rv = SearchEntry(node, global_index=global_index)
                    rv.what = result.group(2).strip().replace('\\"', '"')
                    ## Strip unneeded text tags (anything that's not a time tag)
                    rv.what = re.sub("({(?!time).*?})", "", rv.what)
                    if speaker=="None":
                        rv.who = who_title
                        rv.type ="title"
                    else:
                        rv.who = renpy.ast.eval_who(speaker, True)
                
                elif "SearchTitle" in node.code.source:
                    scene_name = re.search('SearchTitle\("(.*?)"\)', node.code.source).group(1)
                    rv = SearchEntry(node, entry_type="title", what=scene_name, who=who_title, global_index=global_index)
                    self.scene_titles.append(rv)
                
                elif "ShowQuestion" in node.code.source:
                    question_name = re.search("['\"](.*?)['\"]", node.code.source).group(1).strip()
                    question = c5_answers.GetQuestion(question_name)
                    answer = c5_answers.GetAnswer(question_name)
                    
                    if question.type == "character":
                        what = "    Character Select\n    {}".format(question.prompt)
                    elif question.type == "map":
                        what = "    Map Select\n    {}".format(question.prompt)
                    elif question.type == "text":
                        what = "    Text Input\n    {}".format(question.prompt)
                    elif question.type == "choice":
                        temp = python_list()
                        for item in question.choices:
                            chosen = renpy.game.persistent._chosen.get((node.name, item[0]), False)
                            if chosen:
                                temp.append("{color=#fc8}    "+item[0]+"{/color}")
                            else:
                                temp.append("{color=#f88}    "+item[0]+"{/color}")
                        what = '\n'.join(temp)
                    
                    if answer != "":                  
                        if persistent.finished:
                            what += "\n    ({}, Answered: {})".format("Correct" if c5_answers.IsCorrectAnswer(question_name) else "Incorrect", answer)
                        else:
                            what += "\n    (Answered: {})".format(answer)
                    
                    rv = SearchEntry(node, entry_type="choice2", what=what, who=store.who_choice, global_index=global_index)
                
                elif "renpy.input" in node.code.source:
                    rv = SearchEntry(node, entry_type="choice2", what="    Text Input", who=store.who_choice, global_index=global_index)
                
                elif "CallCharacterSelect" in node.code.source:
                    rv = SearchEntry(node, entry_type="choice2", what="    Character Select", who=store.who_choice, global_index=global_index)
                elif "CallMapSelect"  in node.code.source:
                    rv = SearchEntry(node, entry_type="choice2", what="    Map Select", who=store.who_choice, global_index=global_index)
            
            elif type(node)==renpy.ast.Menu:
                rv = SearchEntry(node, entry_type="choice", who=store.who_choice, global_index=global_index)
            
            elif type(node)==renpy.ast.Label:
                if "tip_" in node.name:
                    tip_name = node.name[len("tip_"):]
                    rv = SearchEntry(node, entry_type="title", what=tip_list[tip_name], who=who_title, global_index=global_index)
                    self.scene_titles.append(rv)
            
            return rv
        
        
        def InitializeSearchEntries(self):            
            ## Delete entries that no longer exist in the script (ie. due to script change)
            for key in reversed(renpy.game.persistent._seen_ever.keys()):
                if key not in renpy.game.script.namemap:
                    del renpy.game.persistent._seen_ever[key]
            
            ## Get the indices for the script and tips, arrange them, then read all entries
            script_idxs = [
                GetGlobalIndexFromNode(self.start_node),
                GetGlobalIndexFromNode(self.end_node)
                ]
            tip_idxs = [
                GetGlobalIndexFromNode(self.start_node_tips),
                GetGlobalIndexFromNode(self.end_node_tips)
                ]
            
            if tip_idxs[0]>script_idxs[0]:
                file_idxs = [tip_idxs, script_idxs]
            else:
                file_idxs = [script_idxs, tip_idxs]
            
            ## Create entries for every valid script line
            for temp_idxs in file_idxs:
                for idx in range(temp_idxs[0], temp_idxs[1]):
                    entry = self.CreateSearchEntry(idx)
                    if entry:
                        self.all_entries[entry.label] = entry
            
            ## Sort the final lists
            ## Actually not needed since lists are already sorted by global index due to how they're created
            #self.all_entries = OrderedDict(sorted(self.all_entries.items(), key=lambda kv: kv[1].global_index))
            #self.all_entries.sort(key=lambda x: x.global_index)
            
            self.scene_titles.sort(key=lambda x: x.global_index)
        
        
        def UpdateMessages(self, initial_entry=None, update_gui=False):
            ## Clear search highlights if last search was blank
            if update_gui: # and persistent.search_clear_initial:
                self.ExitMenu()
            
            ## Each entry looks like the following: (filename, date modified, statement number)
            seen_labels = renpy.game.persistent._seen_ever
            current_label = None
            
            for context in renpy.game.contexts[::-1]:
                ## Go through the contexts from top to bottom
                ## This allows us to set current label to tips if we're on a tip
                
                if len(context.current)==3 and context.current[0] in ["game/script.rpy", "game/tips.rpy"]:
                    if current_label is None:
                        current_label = context.current
                    if context.current not in seen_labels:
                        seen_labels[context.current] = True
            
            ## Check if we have new entries
            ## @TODO: This implementation will create delay on load any time a new line is read
            
            if True: #(len(seen_labels) != self.len_entries):
                self.len_entries = len(seen_labels)
                
                ## Get a list of seen game lines
                for e in seen_labels:
                    if (len(e)!=3) or (e in self.processed_labels) or (e not in self.all_entries):
                        continue
                    
                    self.processed_labels[e] = True
                    self.seen_entries_all.append(self.all_entries[e])
                
                ## Add titles
                for entry in self.scene_titles:
                    self.seen_entries_all.append(entry)
                
                ## Sort by index number
                self.seen_entries_all.sort(key=lambda x: x.global_index)
                
                ## Knock out titles that aren't followed by text
                for e_idx in range(len(self.seen_entries_all)-1,0,-1):
                    if self.seen_entries_all[e_idx].type == 'title' and self.seen_entries_all[e_idx-1].type == 'title':
                        self.seen_entries_all.pop(e_idx-1)
                    
                    elif self.seen_entries_all[e_idx].type == 'choice2':
                        ## Update player answer nodes
                        global_index = self.seen_entries_all[e_idx].global_index
                        self.seen_entries_all[e_idx] = self.CreateSearchEntry(global_index)
                        
                if self.seen_entries_all[-1].type == 'title':
                    self.seen_entries_all.pop()
                
                output = python_list()
                new_speakers_found = False
                chapter = 0
                
                def appendChapterData(self, chapter, output):
                    if new_speakers_found:
                        if persistent.tip_visibility["example1"]>0:
                            self.speaker_enabled[chapter][chr_tip.name] = [True, chr_tip]
                        self.speaker_enabled[chapter] = OrderedDict(sorted(self.speaker_enabled[chapter].items()))
                    self.seen_entries_by_chapter[chapter] = output
                    
                    ## Number the statements
                    for ti, tm in enumerate(self.seen_entries_by_chapter[chapter]):
                        tm.search_index = ti
                        tm.chapter = chapter
                
                for e in self.seen_entries_all:
                    if chapter < 5 and e.global_index >= self.chapter_global_idxs[chapter+1]:
                        ## Moving to the next chapter, process everything we got for the last chapter
                        appendChapterData(self, chapter, output)
                        new_speakers_found = False
                        chapter += 1
                        output = python_list()
                    
                    output.append(e)
                    
                    if e.type == 'choice':
                        if chr_choice.name not in self.speaker_enabled[chapter]:
                            self.speaker_enabled[chapter][chr_choice.name] = [True, chr_choice]
                            new_speakers_found = True
                        
                    else:
                        if type(e.who)==NVLCharacter2 and e.who.name and (e.who.data.name not in self.speaker_enabled[chapter]):
                            self.speaker_enabled[chapter][e.who.data.name] = [True, e.who.data]
                            new_speakers_found = True
                
                ## A final sort for C5
                appendChapterData(self, chapter, output)
            
            if update_gui:
                ## Get the current node
                if initial_entry:
                    align_top = True
                    current_node = GetNodeFromGlobalIndex(initial_entry)
                #elif self.current_idx > -1:
                #    align_top = True
                #    current_node = self.seen_entries_by_chapter[self.chapter][self.current_idx].node
                else:
                    align_top = False
                    
                    if current_label is None:
                        current_node = None
                    else:
                        current_node = renpy.game.script.lookup(current_label)
                
                ## Set up the first line in view
                upper_limit = None
                temp_idx = -1
                if current_node:
                    self.chapter = -1
                    node_idx = GetGlobalIndexFromNode(current_node)
                    while self.chapter < 5 and node_idx >= self.chapter_global_idxs[self.chapter+1]:
                        self.chapter += 1
                    
                    ## Get the closest message (has to be done this way if you're currently skipping/transitioning)
                    if len(self.seen_entries_by_chapter[self.chapter])>0:
                        for m in self.seen_entries_by_chapter[self.chapter]:
                            temp_idx = m.search_index
                            if m.global_index >= node_idx:
                                break
                        
                        if align_top:
                            self.current_idx = temp_idx
                            upper_limit = self.current_idx+15
                            
                        else:
                            ## Push the entry to the bottom of the page
                            count = 0
                            total_height = -self.vbox_spacing 
                            view_width  = 978 #@CHECK: Update this with the value of search.view.width
                            view_height = 496+5 #@CHECK: Update this with the value of search.view.height
                            ## The offset allows the lowest entry to partially overflow if needed to keep it flush with the bottom
                            
                            while True:
                                if temp_idx-count == -1:
                                    break
                                
                                widget = self.CreateDisplayableEntry(temp_idx-count)
                                offset = widget.render(view_width,0,0,0).height + self.vbox_spacing
                                
                                if offset+total_height > view_height:
                                    break
                                
                                total_height += offset
                                count += 1
                                self.current_idx = temp_idx-count+1
                            
                            if temp_idx-count > -1:
                                upper_limit = self.current_idx+count
                
                self.Populate(upper_limit, highlight_idx=temp_idx)
        
        def GetSpeakerCategories(self):
            special_chars = python_list()
            main_chars = python_list()
            side_chars = python_list()
            
            for speaker, data in self.speaker_enabled[search.chapter].items():
                if data[1].category=='special':
                    special_chars.append(data[1])
                elif data[1].category=='main':
                    main_chars.append(data[1])
                elif data[1].category=='side':
                    side_chars.append(data[1])
            
            return special_chars, main_chars, side_chars
    
    class ToggleSpeaker(Action, DictEquality):
        def __init__(self, speaker):
            self.speaker = speaker
            
        def __call__(self):
            if self.speaker in search.speaker_enabled[search.chapter]:
                search.speaker_enabled[search.chapter][self.speaker][0] = not search.speaker_enabled[search.chapter][self.speaker][0]
        
        def get_selected(self):
            if self.speaker in search.speaker_enabled[search.chapter]:
                return search.speaker_enabled[search.chapter][self.speaker][0]
            else:
                return False
    
    search = Search()

screen search(initial_entry=None):
    predict False ## Avoid predicting this screen
    tag menu

    default filter_visible = False
    default menu_visible = False
    default menu_position = (0,0)
    default clicked_node = None
    default clicked_note_entry = None

    key "mousedown_1" action search.hide_menus
    key "K_RETURN" action search.hide_menus
    
    use game_menu(_("Search"), padded=(20, 40, 32, 29)):
        hbox:
            frame:
                style "titled_frame"
                top_padding 10
                xsize 230
                ysize 591
                
                vbox:
                    
                    label _("FIND") text_ypos 5 style "frame_title"
                    null height 11
                    frame:
                        background Frame("gui/search_input.png", Borders(11,11,11,11), tile=False)
                        padding (10,5,10,5)
                        xsize 200
                        yminimum 33
                        add search.input
                    
                    null height 5
                    hbox:
                        xalign 0.5
                        textbutton "Prev" action search.hide_menus+[Function(search.Previous)] activate_sound "sounds/sys25.wav"
                        null width 60
                        textbutton "Next" action search.hide_menus+[Function(search.Next)] activate_sound "sounds/sys25.wav"
                    
                    null height 20
                    vbox:
                        style_prefix "check"
                        spacing 8
                        textbutton _("Exact Match") action [ToggleField(persistent, "search_exact_match"), Function(search.InputChanged)] tooltip "Match the word order. If not checked, each word is searched separately." activate_sound "sounds/sys10.wav"
                        textbutton _("Case Sensitive") action ToggleField(persistent, "search_case_sensitive"), Function(search.InputChanged) tooltip "Treat uppercase and lowercase letters differently." activate_sound "sounds/sys10.wav"
                        button:
                            text _("Clear Automatically"):
                                style "check_button_text"                               
                            action ToggleField(persistent, "search_clear_initial")
                            tooltip "Clear results when you leave the menu."
                            activate_sound "sounds/sys10.wav"
                    
                    null height 20
                    python:
                        name_text = ""
                        if search.is_all_speakers_enabled:
                            name_text = "All"
                        else:
                            count = 0
                            for speaker, val in search.speaker_enabled[search.chapter].items():
                                if val[0]:
                                    count += 1
                                    if name_text == "":
                                        name_text = speaker
                        
                            if count==0:
                                name_text = "None"
                            elif count>1:
                                name_text = "{} + {} more".format(name_text, count-1)

                            name_text = "{color=#f88}" + name_text + "{/color}"
                                
                        name_text = "Filter by Name\n{size=15}" + name_text + "{/size}"
                                    
                    textbutton name_text action [SetScreenVariable("menu_visible", False), ToggleScreenVariable("filter_visible")] tooltip "Only show results that match the selected speaker(s)." 
                    
                    null height 20
                    text "":
                        id "search_lines"
                        size 18
                        
                    null height 20
                    text "":
                        id "search_notification"
                        size 18
                        
                    null height 20
                    text "{color=#F00}"+search.error+"{/color}":
                        id "search_error"
                        size 18
                    
                if GetTooltip():
                    text GetTooltip() size 16 yalign 0.94 xalign 0.5
            
            null width 10
            
            frame:
                style "titled_frame"
                padding (5, 5, 5, 15)
                vbox:
                    hbox:
                        style_prefix "search_chapter"
                        spacing 4
                        xoffset 20
                        text "CHAPTER" style "frame_title_text" yalign 0.5
                        null width 20
                        if len(search.seen_entries_by_chapter[0])>0:
                            textbutton "1":
                                action search.hide_menus+[SetVariable("search.chapter", 0), Function(search.SetChapter)]
                                selected search.chapter==0
                        if len(search.seen_entries_by_chapter[1])>0:
                            textbutton "2":
                                action search.hide_menus+[SetVariable("search.chapter", 1), Function(search.SetChapter)]
                                selected search.chapter==1
                        if len(search.seen_entries_by_chapter[2])>0:
                            textbutton "3":
                                action search.hide_menus+[SetVariable("search.chapter", 2), Function(search.SetChapter)]
                                selected search.chapter==2
                        if len(search.seen_entries_by_chapter[3])>0:
                            textbutton "4":
                                action search.hide_menus+[SetVariable("search.chapter", 3), Function(search.SetChapter)]
                                selected search.chapter==3
                        if len(search.seen_entries_by_chapter[4])>0:
                            textbutton "5":
                                action search.hide_menus+[SetVariable("search.chapter", 4), Function(search.SetChapter)]
                                selected search.chapter==4
                        if len(search.seen_entries_by_chapter[5])>0:
                            textbutton "TIPS":
                                action search.hide_menus+[SetVariable("search.chapter", 5), Function(search.SetChapter)]
                                selected search.chapter==5

                    hbox:
                        vbox:
                            label "" id "search_view_title" style "search_scene"
                            massive_viewport:
                                id "search_view"
                                scroll_action search.Scroll
                                arrowkeys True
                                #style_prefix "search"
                                
                                vbox:
                                    style_prefix "search"
                                    id "search_view_vbox"
                                    spacing search.vbox_spacing
                        vbar:
                            id "search_view_bar"
                            value FieldValue(search, "current_idx", search.max_top_idx, action=search.Populate, style="scrollbar")
                            bar_invert True
        
        showif filter_visible:
            frame:
                style_prefix "search_popup"
                xoffset 226
                yalign 0.5
                #yoffset -28
                #yoffset 77
                xsize 400
                at tf_dropdown_menu
            
                vbox:
                    textbutton _("Check All") text_color '#FFF' text_hover_color '#cce6ff' action Function(search.EnableAllSpeakers, True) xfill True
                    textbutton _("Check None") text_color '#FFF' text_hover_color '#cce6ff' action Function(search.EnableAllSpeakers, False) xfill True
                    
                    vbox:
                        style_prefix "check"
                        
                        python:
                            special_chars, main_chars, side_chars = search.GetSpeakerCategories()
                        
                        for char in [special_chars, main_chars, side_chars]:
                            python:
                                if len(char)%2==0:
                                    L = len(char)//2
                                else:
                                    L = len(char)//2 + 1
                            hbox:
                                vbox:
                                    xsize 200
                                    for c in char[:L]:
                                        textbutton _(c.name):
                                            action [ToggleSpeaker(c.name), Function(search.InputChanged)]
                                            xfill True
                                            activate_sound "sounds/sys10.wav"
                                            
                                vbox:
                                    xsize 200
                                    for c in char[L:]:
                                        textbutton _(c.name):
                                            action [ToggleSpeaker(c.name), Function(search.InputChanged)]
                                            xfill True
                                    
                                    ## Put a blank entry so the mouse doesn't select the entries under it
                                    if L > len(char)//2:
                                        textbutton _(""):
                                            action NullAction()
                                            foreground None
                                            xfill True
                            
                            if (char==special_chars and len(main_chars)>0) or (char==main_chars and len(side_chars)>0):
                                button:
                                    add Solid("#fff8", xsize=350, ysize=2, xoffset=-10, yoffset=1)
                                    action NullAction()
                                    foreground None
                                    xfill True

        showif menu_visible:
            frame:
                style_prefix "search_popup"
                xpos menu_position[0]
                ypos menu_position[1]
                xsize 160
                at tf_dropdown_menu
                
                vbox:
                    textbutton _("Jump in-game"):
                        action search.hide_menus+[JumpToScriptNode(clicked_node, confirm=False)]
                        if store._in_replay:
                            activate_sound "sounds/sys18.wav"
                        else:
                            activate_sound "sounds/sys8.wav"
                    textbutton _("Go to note"):
                        if not persistent.notes:
                            action search.hide_menus+[ShowMenu('notes_tutorial')]
                        else:
                            action search.hide_menus+[ShowMenu('notes', clicked_note_entry)]
                    textbutton _("Copy"):
                        action search.hide_menus+[Function(search.Copy, clicked_node)]

    for k in ["hide", "replaced"]:
        on k action [Function(search.ExitMenu), Function(enableEnterSelect, True)]
    for k in ["show", "replace"]:
        on k action Function(enableEnterSelect, False)
    
    ## As much as I dislike the timer, the vbox must first be created fully before I can add stuff to it
    timer 0.01 action Function(search.UpdateMessages, initial_entry, update_gui=True)

style search_window is empty
style search_name is gui_label
style search_text is gui_text
style search_label is gui_label
style search_label_text is gui_label_text
style search_button_text is gui_button_text
style search_vslider is vslider

style search_window:
    xfill True
    ysize gui.history_height

style search_name:
    xpos gui.history_name_xpos
    xanchor gui.history_name_xalign
    ypos gui.history_name_ypos
    xsize gui.history_name_width

style search_name_text:
    min_width gui.history_name_width
    text_align gui.history_name_xalign
    size gui.text_size

style search_what_text:
    size 20 #gui.text_size

style search_text:
    xpos gui.history_text_xpos
    ypos gui.history_text_ypos
    xanchor gui.history_text_xalign
    xsize 400 #gui.history_text_width
    min_width gui.history_text_width
    text_align gui.history_text_xalign
    layout ("subtitle" if gui.history_text_xalign else "tex")

style search_input is input:
    color '#666'
    caret At(Solid("#666", style='search_input_caret'), caret_blink)
    size 18

style search_input_solid is search_input:
    caret At(Solid("#666", style='search_input_caret'), caret_solid)

style search_input_caret:
    xsize 1
    ysize 20

style search_scene:
    xfill True
    background None
    padding (5,5,5,5)

style search_label:
    xfill True

style search_label_text:
    xalign 0

style search_button is gui_button:
    xfill True
    activate_sound None
    hover_sound None

style search_button0 is search_button:
    background "#0003"
    hover_background "#0FF6"

style search_button1 is search_button:
    background "#0008"
    hover_background "#0FF6"
    
style search_button0_found is search_button:
    background "#168edb55"
    hover_background "#0FF6"

style search_button1_found is search_button:
    background "#168edb88"
    hover_background "#0FF6"

style search_button_current is search_button:
    background "#fff3"
    hover_background "#0FF6"

style search_tip is search_button:
    background "#f886"
    hover_background "#0FF6"

style search_chapter_button:
    xsize 100
    ysize 37
    yoffset -3
    background Frame("gui/chapter_button_idle.png", Borders(15,15,15,15))
    hover_background Frame("gui/chapter_button_hover.png", Borders(15,15,15,15))
    selected_idle_background Frame("gui/chapter_button_selected.png", Borders(15,15,15,15))
    
style search_chapter_button_text:
    xalign 0.5
    yalign 0.5
    yoffset 3

style search_popup_frame is popup_frame
style search_popup_button is popup_button
style search_popup_button_text is popup_button_text
