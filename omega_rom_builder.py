import os
import curses
import json
import time

# --- Configuration ---
BLOCK_SIZE = 16 * 1024  # 16KB
MAX_BLOCKS = 16  # 256KB total

# SAVE STATE FILE FOR SELECTIONS
SELECTIONS_FILE = "omega_rom_selections.json"


# --- Patch Selections ---
# These are defaults; can be toggled in the UI
APPLY_INT_KEYBOARD_PATCH = True
APPLY_BACKSLASH_PATCH = True


# --- File Picker ---
def list_all_files(dirs):
    file_list = []
    for directory in dirs:
        for root, _, files in os.walk(directory):
            for f in files:
                rel_dir = os.path.relpath(root, directory)
                rel_file = (
                    os.path.join(directory, rel_dir, f)
                    if rel_dir != "."
                    else os.path.join(directory, f)
                )
                file_list.append(rel_file)
    return sorted(file_list)


def select_file(stdscr, files, slot_name):
    curses.curs_set(0)
    selected = 0
    offset = 0
    h, w = stdscr.getmaxyx()
    win_height = min(20, h - 4)
    win_width = min(60, w - 4)
    win_y = (h - win_height) // 2
    win_x = (w - win_width) // 2
    max_display = win_height - 4
    size_col = 10
    name_col = win_width - size_col - 4
    win = curses.newwin(win_height, win_width, win_y, win_x)
    win.keypad(True)
    search_buffer = ""
    last_key_time = 0
    SEARCH_TIMEOUT = 1.0
    while True:
        win.clear()
        win.box()
        title = f" Select {slot_name} "
        win.addstr(0, (win_width - len(title)) // 2, title, curses.A_BOLD)
        if search_buffer:
            win.addstr(1, 2, f"Search: {search_buffer}", curses.A_DIM)
        for idx, fname in enumerate(files[offset : offset + max_display]):
            y = idx + 2
            # Show last directory and filename
            dirpart = os.path.basename(os.path.dirname(fname))
            if dirpart and dirpart != ".":
                display_name = f"{dirpart}/{os.path.basename(fname)}"[:name_col]
            else:
                display_name = os.path.basename(fname)[:name_col]
            try:
                size_kb = os.path.getsize(fname) // 1024
            except Exception:
                size_kb = 0
            display_size = f"{size_kb} KB"
            line = f"{display_name:<{name_col}}  {display_size:>{size_col}}"
            if idx + offset == selected:
                win.attron(curses.color_pair(1))
            win.addstr(y, 2, line[: win_width - 4])
            if idx + offset == selected:
                win.attroff(curses.color_pair(1))
        win.refresh()
        key = win.getch()
        now = time.time()
        if search_buffer and now - last_key_time > SEARCH_TIMEOUT:
            search_buffer = ""
        last_key_time = now
        if key == curses.KEY_UP and selected > 0:
            selected -= 1
        elif key == curses.KEY_DOWN and selected < len(files) - 1:
            selected += 1
        elif key == ord("\n"):
            return files[selected]
        elif key == 27:
            return None
        elif 32 <= key <= 126:
            ch = chr(key).lower()
            if len(search_buffer) < 5:
                search_buffer += ch
            else:
                search_buffer = search_buffer[1:] + ch
            found = False
            for i, fname in enumerate(files):
                dirpart = os.path.basename(os.path.dirname(fname))
                if dirpart and dirpart != ".":
                    search_name = f"{dirpart}/{os.path.basename(fname)}"
                else:
                    search_name = os.path.basename(fname)
                if search_name.lower().startswith(search_buffer):
                    selected = i
                    found = True
                    break
            if not found:
                for i, fname in enumerate(files):
                    dirpart = os.path.basename(os.path.dirname(fname))
                    if dirpart and dirpart != ".":
                        search_name = f"{dirpart}/{os.path.basename(fname)}"
                    else:
                        search_name = os.path.basename(fname)
                    if search_name.lower().startswith(ch):
                        selected = i
                        break
        else:
            search_buffer = ""
        if selected < offset:
            offset = selected
        elif selected >= offset + max_display:
            offset = selected - max_display + 1


def save_selections(block_files, block_paths):
    data = {
        "block_files": block_files,
        "block_paths": block_paths,
    }
    with open(SELECTIONS_FILE, "w") as f:
        json.dump(data, f)


def load_selections():
    if os.path.exists(SELECTIONS_FILE):
        try:
            with open(SELECTIONS_FILE, "r") as f:
                data = json.load(f)
            return data.get("block_files", []), data.get("block_paths", [])
        except Exception:
            pass
    return None, None


def pick_files():
    # Each slot block: (slot_name, block_index)
    slot_blocks = (
        [("SLOT 0", i) for i in range(4)]
        + [("SLOT 3-0", i) for i in range(4)]
        + [("SLOT 3-1", i) for i in range(4)]
        + [("SLOT 3-3", i) for i in range(4)]
    )
    block_files, block_paths = load_selections()
    if (
        not block_files
        or not block_paths
        or len(block_files) != 16
        or len(block_paths) != 16
    ):
        block_files = [None] * 16
        block_paths = [None] * 16

    def curses_main(
        stdscr,
    ):
        curses.curs_set(0)  # Hide the cursor for the entire UI session
        nonlocal block_files, block_paths, slot_blocks
        global APPLY_INT_KEYBOARD_PATCH, APPLY_BACKSLASH_PATCH
        addr_labels = [
            "0000H~3FFFH",
            "4000H~7FFFH",
            "8000H~BFFFH",
            "C000H~FFFFH",
        ]
        block_w = 14  # Fixed width for all slot blocks

        def center_block_text(text):
            return text.center(block_w - 2)

        # --- Enhanced color palette: use 256-color mode if available ---
        curses.start_color()
        if hasattr(curses, "COLORS") and curses.COLORS >= 256:
            curses.use_default_colors()
            # Blue gradient theme: from dark to light blue
            curses.init_pair(
                1, 231, 196
            )  # Selection highlight: white on red (keep for visibility)
            curses.init_pair(2, 231, 17)  # BIOS: white on dark blue (navy)
            curses.init_pair(3, 231, 18)  # LOGO: white on dark blue
            curses.init_pair(4, 231, 19)  # SUBROM: white on blue3
            curses.init_pair(5, 231, 20)  # KANJI: white on blue1
            curses.init_pair(6, 231, 21)  # DISK: white on blue
            curses.init_pair(7, 231, 39)  # KUN/MUSIC: white on deep sky blue
            curses.init_pair(8, 231, 16)  # Inverted selection: white on black
            curses.init_pair(9, 231, 33)  # EXTRAS: white on dodger blue
        else:
            curses.init_pair(
                1, curses.COLOR_WHITE, curses.COLOR_RED
            )  # Selection highlight: white on red
            curses.init_pair(
                2, curses.COLOR_WHITE, curses.COLOR_BLUE
            )  # BIOS: white on blue
            curses.init_pair(
                3, curses.COLOR_WHITE, curses.COLOR_BLUE
            )  # LOGO: white on blue
            curses.init_pair(
                4, curses.COLOR_WHITE, curses.COLOR_BLUE
            )  # SUBROM: white on blue
            curses.init_pair(
                5, curses.COLOR_WHITE, curses.COLOR_BLUE
            )  # KANJI: white on blue
            curses.init_pair(
                6, curses.COLOR_WHITE, curses.COLOR_BLUE
            )  # DISK: white on blue
            curses.init_pair(
                7, curses.COLOR_WHITE, curses.COLOR_CYAN
            )  # KUN/MUSIC: white on cyan (lighter blue)
            curses.init_pair(8, curses.COLOR_WHITE, curses.COLOR_BLACK)
            curses.init_pair(
                9, curses.COLOR_WHITE, curses.COLOR_CYAN
            )  # EXTRAS: white on cyan
        color_main = curses.color_pair(2)
        color_logo = curses.color_pair(3)
        color_subrom = curses.color_pair(4)
        color_kanji = curses.color_pair(5)
        color_disk = curses.color_pair(6)
        color_333 = curses.color_pair(7)
        color_extras = curses.color_pair(9)
        selected_block = 0
        while True:
            stdscr.clear()
            stdscr.addstr(0, 0, "Omega MSX ROM Builder", curses.A_BOLD)
            # Get terminal size once per loop
            h, w = stdscr.getmaxyx()
            # Draw blocks and highlight selection
            # Calculate total_kb before drawing UI (only once)
            total_kb = 0
            for i in range(16):
                if block_files[i] and block_paths[i]:
                    fpath = block_paths[i]
                    try:
                        fsize = os.path.getsize(fpath)
                    except Exception:
                        fsize = 0
                    blocks = max(
                        1,
                        min(
                            (fsize + 16 * 1024 - 1) // (16 * 1024), 16 - i, 4 - (i % 4)
                        ),
                    )
                    total_kb += blocks * 16 * 1024 // 1024
            # Count number of used files (unique, non-None)
            used_files = len([f for f in block_files if f])
            # Patch status for status bar (now to be shown above Selected files)
            patch_status_1 = f"[{'X' if APPLY_INT_KEYBOARD_PATCH else ' '}] International Keyboard [F2]"
            patch_status_2 = (
                f"[{'X' if APPLY_BACKSLASH_PATCH else ' '}] Backslash Yen [F3]"
            )
            slot0_y = 2
            slot0_x = 2
            slot3_0_x = slot0_x + 28
            slot3_1_x = slot3_0_x + 16
            slot3_2_x = slot3_1_x + 16
            # Draw SLOT 0, SLOT 3-0, SLOT 3-1, SLOT 3-3 blocks (side by side, only one set of address labels)
            i = 0
            while i < 4:
                y = slot0_y + (3 - i) * (1 + 0)
                block_idx = i
                highlight = selected_block == block_idx
                fill = None
                color = 0
                skip_blocks = 1
                if block_files[block_idx] and block_paths[block_idx]:
                    fname = block_files[block_idx].lower()
                    fpath = block_paths[block_idx]
                    try:
                        fsize = os.path.getsize(fpath)
                    except Exception:
                        fsize = 0
                    blocks = max(1, min((fsize + 16 * 1024 - 1) // (16 * 1024), 4 - i))
                    skip_blocks = blocks
                    if "logo" in fname:
                        fill = "LOGO"
                        color = color_logo if not highlight else curses.color_pair(1)
                    else:
                        fill = "BIOS"
                        color = color_main if not highlight else curses.color_pair(1)
                else:
                    color = curses.color_pair(1) if highlight else 0
                stdscr.addstr(y, slot0_x, f"{addr_labels[i]} ")
                text = center_block_text(fill if fill else "")
                stdscr.addstr(y, slot0_x + 12, "[", 0)
                stdscr.addstr(y, slot0_x + 13, f" {text} ", color)
                stdscr.addstr(y, slot0_x + 13 + len(f" {text} "), "]", 0)
                for j in range(1, skip_blocks):
                    if i + j < 4:
                        y2 = slot0_y + (3 - (i + j)) * (1 + 0)
                        highlight2 = selected_block == (block_idx + j)
                        color2 = color if not highlight2 else curses.color_pair(1)
                        stdscr.addstr(y2, slot0_x, f"{addr_labels[i + j]} ")
                        text2 = center_block_text(fill if fill else "")
                        stdscr.addstr(y2, slot0_x + 12, "[", 0)
                        stdscr.addstr(y2, slot0_x + 13, f" {text2} ", color2)
                        stdscr.addstr(y2, slot0_x + 13 + len(f" {text2} "), "]", 0)
                i += skip_blocks
            # SLOT 3-0
            i = 0
            while i < 4:
                y = slot0_y + (3 - i) * (1 + 0)
                block_idx = 4 + i
                highlight = selected_block == block_idx
                fill = None
                color = 0
                skip_blocks = 1
                if block_files[block_idx] and block_paths[block_idx]:
                    fname = block_files[block_idx].lower()
                    fname_lower = fname.lower()
                    fpath = block_paths[block_idx]
                    try:
                        fsize = os.path.getsize(fpath)
                    except Exception:
                        fsize = 0
                    blocks = max(1, min((fsize + 16 * 1024 - 1) // (16 * 1024), 4 - i))
                    skip_blocks = blocks
                    if block_idx < 4:
                        if "logo" in fname_lower:
                            fill = "LOGO"
                            color = (
                                color_logo if not highlight else curses.color_pair(1)
                            )
                        else:
                            fill = "BIOS"
                            color = (
                                color_main if not highlight else curses.color_pair(1)
                            )
                    elif block_idx < 8:
                        # Check if file is from extras directory
                        is_from_extras = "extras/" in fpath
                        if "kanji" in fname_lower:
                            fill = "KANJI"
                            color = color_kanji
                        elif "sub" in fname_lower:
                            fill = "SUBROM"
                            color = color_subrom
                        elif "ext" in fname_lower:
                            fill = "EXT"
                            color = color_subrom
                        elif is_from_extras:
                            # Files from extras directory get special color
                            base = fname.split(".")[0]
                            fill = base[:8].upper()
                            color = color_extras
                        else:
                            # Capitalize, remove dot and all after if present
                            base = fname.split(".")[0]
                            fill = base[:8].upper()
                            color = color_subrom
                        if highlight:
                            color = curses.color_pair(1)
                    elif block_idx < 12:
                        if "disk" in fname_lower:
                            fill = "DISK"
                            color = color_disk
                        else:
                            base = fname.split(".")[0]
                            fill = base[:8].upper()
                            color = color_disk
                        if highlight:
                            color = curses.color_pair(1)
                    else:
                        if any(x in fname_lower for x in ("kun", "music", "fm")):
                            fill = "KUN/MUS"
                            color = color_333
                        else:
                            base = fname.split(".")[0]
                            fill = base[:8].upper()
                            color = color_333
                        if highlight:
                            color = curses.color_pair(1)
                else:
                    color = curses.color_pair(1) if highlight else 0
                    fill = ""
                text = center_block_text(fill if fill else "")
                stdscr.addstr(y, slot3_0_x, "[", 0)
                stdscr.addstr(y, slot3_0_x + 1, f" {text} ", color)
                stdscr.addstr(y, slot3_0_x + 1 + len(f" {text} "), "]", 0)
                for j in range(1, skip_blocks):
                    if i + j < 4:
                        y2 = slot0_y + (3 - (i + j)) * (1 + 0)
                        highlight2 = selected_block == (block_idx + j)
                        color2 = color if not highlight2 else curses.color_pair(1)
                        text2 = center_block_text(fill if fill else "")
                        stdscr.addstr(y2, slot3_0_x, "[", 0)
                        stdscr.addstr(y2, slot3_0_x + 1, f" {text2} ", color2)
                        stdscr.addstr(y2, slot3_0_x + 1 + len(f" {text2} "), "]", 0)
                i += skip_blocks
            # SLOT 3-1
            i = 0
            while i < 4:
                y = slot0_y + (3 - i) * (1 + 0)
                block_idx = 8 + i
                highlight = selected_block == block_idx
                fill = None
                color = 0
                skip_blocks = 1
                if block_files[block_idx] and block_paths[block_idx]:
                    fname = block_files[block_idx].lower()
                    fpath = block_paths[block_idx]
                    try:
                        fsize = os.path.getsize(fpath)
                    except Exception:
                        fsize = 0
                    blocks = max(1, min((fsize + 16 * 1024 - 1) // (16 * 1024), 4 - i))
                    skip_blocks = blocks
                    if "disk" in fname:
                        fill = "DISK"
                        color = color_disk
                    else:
                        # Capitalize, remove dot and all after if present
                        fill = fname.split(".")[0][:8].upper()
                        color = color_disk
                else:
                    color = 0
                    fill = ""
                if highlight:
                    color = curses.color_pair(1)
                text = center_block_text(fill if fill else "")
                stdscr.addstr(y, slot3_1_x, "[", 0)
                stdscr.addstr(y, slot3_1_x + 1, f" {text} ", color)
                stdscr.addstr(y, slot3_1_x + 1 + len(f" {text} "), "]", 0)
                for j in range(1, skip_blocks):
                    if i + j < 4:
                        y2 = slot0_y + (3 - (i + j)) * (1 + 0)
                        highlight2 = selected_block == (block_idx + j)
                        color2 = color if not highlight2 else curses.color_pair(1)
                        text2 = center_block_text(fill if fill else "")
                        stdscr.addstr(y2, slot3_1_x, "[", 0)
                        stdscr.addstr(y2, slot3_1_x + 1, f" {text2} ", color2)
                        stdscr.addstr(y2, slot3_1_x + 1 + len(f" {text2} "), "]", 0)
                i += skip_blocks
            # SLOT 3-3
            i = 0
            while i < 4:
                y = slot0_y + (3 - i) * (1 + 0)
                block_idx = 12 + i
                highlight = selected_block == block_idx
                fill = None
                color = 0
                skip_blocks = 1
                if block_files[block_idx] and block_paths[block_idx]:
                    fname = block_files[block_idx].lower()
                    fpath = block_paths[block_idx]
                    try:
                        fsize = os.path.getsize(fpath)
                    except Exception:
                        fsize = 0
                    blocks = max(1, min((fsize + 16 * 1024 - 1) // (16 * 1024), 4 - i))
                    skip_blocks = blocks
                    if "kun" in fname or "music" in fname or "fm" in fname:
                        if highlight:
                            color = curses.color_pair(1)
                        else:
                            color = color_333
                        if "kun" in fname:
                            fill = "KUN"
                        elif "music" in fname:
                            fill = "MUSIC"
                        elif "fm" in fname:
                            fill = "FM"
                        else:
                            fill = fname[:8]
                    else:
                        fill = fname[:8]
                        color = color_333 if not highlight else curses.color_pair(1)
                else:
                    color = 0
                    fill = ""
                if highlight:
                    color = curses.color_pair(1)
                text = center_block_text(fill if fill else "")
                stdscr.addstr(y, slot3_2_x, "[", 0)
                stdscr.addstr(y, slot3_2_x + 1, f" {text} ", color)
                stdscr.addstr(y, slot3_2_x + 1 + len(f" {text} "), "]", 0)
                for j in range(1, skip_blocks):
                    if i + j < 4:
                        y2 = slot0_y + (3 - (i + j)) * (1 + 0)
                        highlight2 = selected_block == (block_idx + j)
                        color2 = color if not highlight2 else curses.color_pair(1)
                        text2 = center_block_text(fill if fill else "")
                        stdscr.addstr(y2, slot3_2_x, "[", 0)
                        stdscr.addstr(y2, slot3_2_x + 1, f" {text2} ", color2)
                        stdscr.addstr(y2, slot3_2_x + 1 + len(f" {text2} "), "]", 0)
                i += skip_blocks
            # Centered labels above each slot
            slot_label_y = slot0_y - 1  # Place above the first block row
            slot0_label_x = (
                slot0_x + 12 + (len("[   BIOS   ]") // 2) - (len("SLOT 0") // 2)
            )
            slot3_0_label_x = (
                slot3_0_x + (len("[  SUBROM  ]") // 2) - (len("SLOT 3-0") // 2)
            )
            slot3_1_label_x = (
                slot3_1_x + (len("[   DISK   ]") // 2) - (len("SLOT 3-1") // 2)
            )
            slot3_2_label_x = (
                slot3_2_x + (len("[ KUN/MUSIC ]") // 2) - (len("SLOT 3-3") // 2)
            )
            stdscr.addstr(slot_label_y, slot0_label_x + 1, "SLOT 0", curses.A_DIM)
            stdscr.addstr(slot_label_y, slot3_0_label_x + 1, "SLOT 3-0", curses.A_DIM)
            stdscr.addstr(slot_label_y, slot3_1_label_x + 1, "SLOT 3-1", curses.A_DIM)
            stdscr.addstr(slot_label_y, slot3_2_label_x + 1, "SLOT 3-3", curses.A_DIM)

            any_selected = any(block_files[i] for i in range(16))
            # Find where to start the patches section so it doesn't overlap with the block display
            patches_y = slot0_y + 5
            if any_selected:
                stdscr.addstr(patches_y, 0, "Available patches:", curses.A_BOLD)
                stdscr.addstr(patches_y + 1, 2, patch_status_1)
                stdscr.addstr(patches_y + 2, 2, patch_status_2)
                list_y = patches_y + 4
                stdscr.addstr(
                    list_y, 0, f"Selected files ({used_files}):", curses.A_BOLD
                )
                row = list_y + 1
                i = 0
                while i < 16:
                    if block_files[i] and block_paths[i]:
                        fname = block_files[i]
                        fpath = block_paths[i]
                        try:
                            fsize = os.path.getsize(fpath)
                        except Exception:
                            fsize = 0
                        # Calculate how many blocks this file fills
                        blocks = max(
                            1,
                            min(
                                (fsize + 16 * 1024 - 1) // (16 * 1024),
                                16 - i,
                                4 - (i % 4),
                            ),
                        )
                        block_start = i % 4 + 1
                        block_end = block_start + blocks - 1
                        slot_label = slot_blocks[i][0]
                        # Color logic for each slot, but always show the filename as label
                        fname_lower = fname.lower()
                        if i < 4:
                            color = color_logo if "logo" in fname_lower else color_main
                        elif i < 8:
                            # Check if file is from extras directory
                            is_from_extras = "extras/" in fpath
                            if "kanji" in fname_lower:
                                color = color_kanji
                            elif "sub" in fname_lower:
                                color = color_subrom
                            elif is_from_extras:
                                color = color_extras
                            else:
                                color = color_subrom
                        elif i < 12:
                            if "disk" in fname_lower:
                                color = color_disk
                            else:
                                color = color_disk
                        else:
                            if (
                                "kun" in fname_lower
                                or "music" in fname_lower
                                or "fm" in fname_lower
                            ):
                                color = color_333
                            else:
                                color = color_333
                        label = fname
                        # Show last directory and filename in selected files list
                        dirpart = os.path.basename(os.path.dirname(fpath))
                        if dirpart and dirpart != ".":
                            label = f"{dirpart}/{fname}"
                        else:
                            label = fname
                        slot_str = f"{slot_label:<8}"
                        block_str = f"block {block_start}"
                        if block_start != block_end:
                            block_str = f"block {block_start}-{block_end}"
                        block_str = f"{block_str:<9}"
                        left = f"{slot_str} {block_str}:"
                        left_padded = f"{left:<22}"
                        stdscr.addstr(row, 2, left_padded, color)
                        stdscr.addstr(f" {label:<28}", color)
                        stdscr.addstr(f"  ({fsize//1024} KB)", color)
                        row += 1
                        i += blocks
                    else:
                        i += 1
                # Add total size line (red background, white text), right-aligned
                total_label = "Total size        :"
                total_str = f"{total_kb} KB "
                total_line_width = 60
                spaces = total_line_width - len(total_label) - len(total_str)
                total_line = total_label + (" " * spaces) + total_str
                stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
                stdscr.addstr(row, 2, total_line)
                stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)
            stdscr.refresh()
            key = stdscr.getch()
            if key in (27,):  # ESC
                save_selections(block_files, block_paths)
                return block_files, block_paths
            elif key == curses.KEY_F2:
                APPLY_INT_KEYBOARD_PATCH = not APPLY_INT_KEYBOARD_PATCH
            elif key == curses.KEY_F3:
                APPLY_BACKSLASH_PATCH = not APPLY_BACKSLASH_PATCH
            elif key in (curses.KEY_UP,):
                if selected_block % 4 < 3:
                    selected_block += 1
            elif key in (curses.KEY_DOWN,):
                if selected_block % 4 > 0:
                    selected_block -= 1
            elif key in (curses.KEY_LEFT,):
                if selected_block >= 4:
                    selected_block -= 4
            elif key in (curses.KEY_RIGHT,):
                if selected_block < 12:
                    selected_block += 4
            elif key in (curses.KEY_DC, 127):  # DEL or Backspace
                if selected_block < 16:
                    block_files[selected_block] = None
                    block_paths[selected_block] = None
            elif key in (ord("\n"), 10, 13):
                if selected_block < 4:
                    files = [
                        f
                        for f in list_all_files(["systemroms/machines"])
                        if "bios" in os.path.basename(f).lower()
                        or "logo" in os.path.basename(f).lower()
                    ]
                elif selected_block < 8:
                    files = [
                        f
                        for f in list_all_files(["systemroms/machines", "extras"])
                        if any(
                            x in os.path.basename(f).lower()
                            for x in ("sub", "kanji", "ext", "msxd")
                        )
                    ]
                elif selected_block < 12:
                    files = [
                        f
                        for f in list_all_files(["systemroms/machines"])
                        if "disk" in os.path.basename(f).lower()
                    ]
                else:
                    files = [
                        f
                        for f in list_all_files(["systemroms/machines"])
                        if any(
                            x in os.path.basename(f).lower()
                            for x in ("kun", "fm", "music")
                        )
                    ]
                pick = select_file(
                    stdscr,
                    files,
                    f"Block {selected_block%4+1} ({slot_blocks[selected_block][0]})",
                )
                if pick is not None:
                    block_files[selected_block] = os.path.basename(pick)
                    block_paths[selected_block] = pick
        # else: ignore other keys

    return curses.wrapper(curses_main)


def build_rom_image(selected_files, selected_paths, output_path):
    # Build a 256KB ROM image from selected files, filling unused blocks with 0xFF
    rom = bytearray([0xFF] * (BLOCK_SIZE * MAX_BLOCKS))
    for i, (fname, fpath) in enumerate(zip(selected_files, selected_paths)):
        if fname and fpath:
            try:
                with open(fpath, "rb") as f:
                    data = f.read(BLOCK_SIZE * (4 - (i % 4)))
                offset = i * BLOCK_SIZE
                rom[offset : offset + len(data)] = data
            except Exception as e:
                print(f"Error reading {fpath}: {e}")
    # Apply patches if enabled
    if APPLY_INT_KEYBOARD_PATCH:
        try:
            with open("patches/int_keys_patch.bin", "rb") as f:
                patch = f.read()
            # Example offset: 3529 (as in your shell script)
            rom[3529 : 3529 + len(patch)] = patch
            print("Applied int_keys_patch.bin at offset 3529")
        except Exception as e:
            print(f"Could not apply int_keys_patch: {e}")
    if APPLY_BACKSLASH_PATCH:
        try:
            with open("patches/backslash_patch.bin", "rb") as f:
                patch = f.read()
            # Example offset: 7839 (as in your shell script)
            rom[7839 : 7839 + len(patch)] = patch
            print("Applied backslash_patch.bin at offset 7839")
        except Exception as e:
            print(f"Could not apply backslash_patch: {e}")
    with open(output_path, "wb") as f:
        f.write(rom)
    print(f"ROM image written to {output_path}")


def main():
    selected_files, selected_paths = pick_files()
    print("\nSelected files:")

    # Define color codes for terminal output
    COLORS = {
        "RESET": "\033[0m",
        "BIOS": "\033[38;5;231m\033[48;5;17m",  # white on dark blue (navy)
        "LOGO": "\033[38;5;231m\033[48;5;18m",  # white on dark blue
        "SUBROM": "\033[38;5;231m\033[48;5;19m",  # white on blue3
        "KANJI": "\033[38;5;231m\033[48;5;20m",  # white on blue1
        "DISK": "\033[38;5;231m\033[48;5;21m",  # white on blue
        "EXTRAS": "\033[38;5;231m\033[48;5;33m",  # white on dodger blue
        "KUN_MUSIC": "\033[38;5;231m\033[48;5;39m",  # white on deep sky blue
    }

    i = 0
    while i < 16:
        if selected_files[i] and selected_paths[i]:
            fname = selected_files[i]
            fpath = selected_paths[i]
            try:
                fsize = os.path.getsize(fpath)
            except Exception:
                fsize = 0

            # Calculate how many blocks this file fills
            blocks = max(
                1, min((fsize + 16 * 1024 - 1) // (16 * 1024), 16 - i, 4 - (i % 4))
            )

            block_start = i + 1
            block_end = block_start + blocks - 1

            # Determine color based on file type and location
            fname_lower = fname.lower()
            color = COLORS["RESET"]

            if i < 4:  # SLOT 0
                if "logo" in fname_lower:
                    color = COLORS["LOGO"]
                else:
                    color = COLORS["BIOS"]
            elif i < 8:  # SLOT 3-0
                is_from_extras = "extras/" in fpath
                if "kanji" in fname_lower:
                    color = COLORS["KANJI"]
                elif "sub" in fname_lower:
                    color = COLORS["SUBROM"]
                elif is_from_extras:
                    color = COLORS["EXTRAS"]
                else:
                    color = COLORS["SUBROM"]
            elif i < 12:  # SLOT 3-1
                color = COLORS["DISK"]
            else:  # SLOT 3-3
                if any(x in fname_lower for x in ("kun", "music", "fm")):
                    color = COLORS["KUN_MUSIC"]
                else:
                    color = COLORS["KUN_MUSIC"]

            # Format block range
            if block_start == block_end:
                block_str = f"Block {block_start:02d}"
            else:
                block_str = f"Block {block_start}-{block_end}"

            # Show last directory and filename
            dirpart = os.path.basename(os.path.dirname(fpath))
            if dirpart and dirpart != ".":
                label = f"{dirpart}/{fname}"
            else:
                label = fname

            print(f"{color}{block_str:9} : {label} ({fsize//1024} KB){COLORS['RESET']}")
            i += blocks
        else:
            block_str = f"Block {i+1:02d}"
            print(f"{block_str:9} : [None]")
            i += 1

    # Build ROM image with patch options
    output_path = "omega_output.bin"
    build_rom_image(selected_files, selected_paths, output_path)


if __name__ == "__main__":
    main()
