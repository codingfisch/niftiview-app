__version__ = '1.0.2'
import sv_ttk
import numpy as np
from sys import argv
from copy import deepcopy
from PIL import Image, ImageTk
from platform import system
from functools import partial
from webbrowser import open_new_tab

from tkinterdnd2 import DND_FILES, TkinterDnD
from tkinter import ttk, filedialog, Tk, Menu, Frame, Toplevel, EventType, BooleanVar
from niftiview.cli import save_gif, save_images_or_gifs
from niftiview.config import PADCOLORS, LINECOLORS, TMP_HEIGHTS, LAYER_ATTRIBUTES, Config
from niftiview.core import PLANES, ATLASES, TEMPLATES, RESIZINGS, LAYOUT_STRINGS, COORDINATE_SYSTEMS, GLASS_MODES
from niftiview.image import QRANGE, CMAPS_IMAGE, CMAPS_MASK
from niftiview.grid import NiftiImageGrid

from niftiview_app.utils import DATA_PATH, CONFIG_DICT, dcm2nii, debounce, get_window_frame, parse_dnd_filepaths
PLANES_4D = tuple(list(PLANES) + ['time'])
SCALINGS = (.5, 2/3, .75, 1, 4/3, 1.5, 2)
PATH_PLACEHOLDER = {'image': '/path/to/images/*.nii (or drag&drop here)',
                    'mask': '/path/to/masks/*.nii (or drag&drop here)'}
OPTIONS = {'Main': ['Height', 'Layout', 'Colormap', 'Mask colormap', 'Mask opacity [%]', 'Max samples', 'Crosshair'],
           'Image': ['Equalize histogram', 'Percentile range', '', 'Value range', '', 'Transparent if', 'Resizing'],
           'Mask': ['Is atlas', 'Percentile range', '', 'Value range', '', 'Transparent if', 'Resizing'],
           'Overlay': ['Coordinates', 'Header', 'Histogram', 'Colorbar', 'Filepath', 'Title', 'Fontsize'],
           'Colorbar': ['Position [%]', '', 'Size [%]', '', 'Padding', 'Label', 'Ticks']}
OPTION_TABS = list(OPTIONS)
FILETYPES = [('Portable Network Graphics', '*.png'), ('JPEG', '*.jpg;*.jpeg'), ('Tagged Image File', '*.tiff;*.tif'),
             ('Portable Document Format', '*.pdf'), ('Scalable Vector Graphics', '*.svg'),
             ('Encapsulated PostScript', '*.eps'), ('PostScript', '*.ps')]
TUTORIAL_URL = 'https://youtu.be/OVUy_wd98Ps'
HOMEPAGE_URL = 'https://github.com/codingfisch/niftiview-app'
AUTHOR_URL = 'https://github.com/codingfisch'
RELEASE_URL = f'{HOMEPAGE_URL}/releases/tag/v{__version__}'
CMD_KEY = 'Meta' if system() == 'Darwin"' else 'Control'


class InputFrame(Frame, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)
        self.grid_columnconfigure(1, weight=1)
        grid_kwargs = {'sticky': 'nsew', 'pady': 2}
        self.image_label = ttk.Label(self, text='Image files')
        self.image_label.grid(row=0, column=0, **grid_kwargs, padx=5)
        self.image_entry = ttk.Entry(self)
        self.image_entry.insert(0, '/path/to/images/*.nii (or drag&drop here)')
        self.image_entry.drop_target_register(DND_FILES)
        self.image_entry.grid(row=0, column=1, **grid_kwargs)
        self.mask_label = ttk.Label(self, text='Mask files')
        self.mask_label.grid(row=1, column=0, **grid_kwargs, padx=5)
        self.mask_entry = ttk.Entry(self)
        self.mask_entry.insert(0, '/path/to/masks/*.nii (or drag&drop here)')
        self.mask_entry.drop_target_register(DND_FILES)
        self.mask_entry.grid(row=1, column=1, **grid_kwargs)


class OptionsFrame(ttk.Frame):
    def __init__(self, *args, **kwargs):
        config = kwargs.pop('config')
        super().__init__(*args, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.tabview = ttk.Notebook(self)
        self.tabview.grid_columnconfigure(0, weight=1)
        for i, (tab_name, option_labels) in enumerate(OPTIONS.items()):
            tab_frame = ttk.Frame(self.tabview)
            self.tabview.add(tab_frame, text=tab_name)
            tab_frame.grid_columnconfigure(0, weight=1)
            tab_frame.grid_columnconfigure(1, weight=0)
            for row, label in enumerate(option_labels):
                label_attr = f'{label}_mask_label' if tab_name == 'Mask' else f'{label}_label'
                label_widget = ttk.Label(tab_frame, text=label)
                setattr(self, label_attr, label_widget)
                label_widget.grid(row=row, column=0, sticky='nsw', padx=5)
            setattr(self, f'tab{i}', tab_frame)

        grid_kwargs = {'pady': 2, 'sticky': 'nswe'}
        self.grid_checkbox_kwargs = {'pady': grid_kwargs['pady'], 'sticky': 'nse'}
        self.height_spinbox = ttk.Spinbox(self.tab0, from_=100, to=2000, increment=100)
        self.height_spinbox.set(config.height)
        self.height_spinbox.grid(row=0, column=1, **grid_kwargs)
        layout_str = LAYOUT_STRINGS[config.layout] if config.layout in LAYOUT_STRINGS else config.layout
        self.layout_options = ttk.Combobox(self.tab0, values=list(LAYOUT_STRINGS), width=5)
        self.layout_options.set(config.layout if layout_str in list(LAYOUT_STRINGS.values()) else None)
        self.layout_options.grid(row=1, column=1, **grid_kwargs)
        self.cmap_options = ttk.Combobox(self.tab0, values=list(CMAPS_IMAGE) + ['CATALOG'])
        self.cmap_options.set(CMAPS_IMAGE[0] if config.cmap is None else config.cmap[0])
        self.cmap_options.grid(row=2, column=1, **grid_kwargs)
        self.cmap_mask_options = ttk.Combobox(self.tab0, values=list(CMAPS_MASK) + ['CATALOG'])
        if config.cmap is None:
            self.cmap_mask_options.set(CMAPS_MASK[0])
        elif isinstance(config.cmap, list) and len(config.cmap) == 1:
            self.cmap_mask_options.set(CMAPS_MASK[0])
        else:
            self.cmap_mask_options.set(config.cmap[-1])
        self.cmap_mask_options.grid(row=3, column=1, **grid_kwargs)
        self.alpha_spinbox = ttk.Spinbox(self.tab0, from_=0, to=100, increment=10)
        self.alpha_spinbox.set(100 * config.alpha)
        self.alpha_spinbox.grid(row=4, column=1, **grid_kwargs)
        self.max_samples_spinbox = ttk.Spinbox(self.tab0, from_=1, to=20)
        self.max_samples_spinbox.set(config.max_samples)
        self.max_samples_spinbox.grid(row=5, column=1, **grid_kwargs)
        self.crosshair_check = BooleanVar(value=config.crosshair)
        self.crosshair_checkbox = ttk.Checkbutton(self.tab0, text='', variable=self.crosshair_check)
        self.crosshair_checkbox.grid(row=6, column=1, **self.grid_checkbox_kwargs)
        self.equal_hist_check = BooleanVar(value=config.equal_hist)
        self.equal_hist_checkbox = ttk.Checkbutton(self.tab1, text='', variable=self.equal_hist_check)
        self.equal_hist_checkbox.grid(row=0, column=1, **self.grid_checkbox_kwargs)
        self.qrange_stop_spinbox = ttk.Spinbox(self.tab1, from_=0, to=100, increment=1)
        self.qrange_stop_spinbox.set(100 * (QRANGE[0][1] if config.qrange[0] is None else config.qrange[0][1]))
        self.qrange_stop_spinbox.grid(row=1, column=1, **grid_kwargs)
        self.qrange_start_spinbox = ttk.Spinbox(self.tab1, from_=0, to=100, increment=1)
        self.qrange_start_spinbox.set(100 * (QRANGE[0][0] if config.qrange[0] is None else config.qrange[0][0]))
        self.qrange_start_spinbox.grid(row=2, column=1, **grid_kwargs)
        self.vrange_stop_spinbox = ttk.Spinbox(self.tab1, from_=-10**-45, to=10**45, increment=.5)
        self.vrange_stop_spinbox.grid(row=3, column=1, **grid_kwargs)
        self.vrange_start_spinbox = ttk.Spinbox(self.tab1, from_=-10**-45, to=10**45, increment=.5)
        self.vrange_start_spinbox.grid(row=4, column=1, **grid_kwargs)
        self.transp_if_entry = ttk.Entry(self.tab1)
        if config.transp_if[0] is not None:
            self.transp_if_entry.insert(0, config.transp_if[0])
        self.transp_if_entry.grid(row=5, column=1, **grid_kwargs)
        self.resizing_options = ttk.Combobox(self.tab1, values=RESIZINGS, state='readonly')
        self.resizing_options.set(RESIZINGS[config.resizing[0]])
        self.resizing_options.grid(row=6, column=1, **grid_kwargs)
        if config.is_atlas is None:
            self.is_atlas_check = BooleanVar(value=True)
        elif isinstance(config.cmap, list) and len(config.cmap) == 1:
            self.is_atlas_check = BooleanVar(value=True)
        else:
            self.is_atlas_check = BooleanVar(value=config.is_atlas[-1])
        self.is_atlas_checkbox = ttk.Checkbutton(self.tab2, text='', variable=self.is_atlas_check)
        self.is_atlas_checkbox.grid(row=0, column=1, **self.grid_checkbox_kwargs)
        self.qrange_stop_mask_spinbox = ttk.Spinbox(self.tab2, from_=0, to=100, increment=1)
        self.qrange_stop_mask_spinbox.set(100 * (config.qrange[-1][1] if len(config.qrange) > 1 else QRANGE[1][1]))
        self.qrange_stop_mask_spinbox.grid(row=1, column=1, **grid_kwargs)
        self.qrange_start_mask_spinbox = ttk.Spinbox(self.tab2, from_=0, to=100, increment=1)
        self.qrange_start_mask_spinbox.set(100 * (config.qrange[-1][0] if len(config.qrange) > 1 else QRANGE[1][0]))
        self.qrange_start_mask_spinbox.grid(row=2, column=1, **grid_kwargs)
        self.vrange_stop_mask_spinbox = ttk.Spinbox(self.tab2, from_=-10**-45, to=10**45, increment=.5)
        self.vrange_stop_mask_spinbox.grid(row=3, column=1, **grid_kwargs)
        self.vrange_start_mask_spinbox = ttk.Spinbox(self.tab2, from_=-10**-45, to=10**45, increment=.5)
        self.vrange_start_mask_spinbox.grid(row=4, column=1, **grid_kwargs)
        self.transp_if_mask_entry = ttk.Entry(self.tab2)
        if config.transp_if[-1] is not None:
            self.transp_if_mask_entry.insert(0, config.transp_if[-1])
        self.transp_if_mask_entry.grid(row=5, column=1, **grid_kwargs)
        self.resizing_mask_options = ttk.Combobox(self.tab2, values=RESIZINGS, state='readonly')
        self.resizing_mask_options.set(RESIZINGS[config.resizing[-1]])
        self.resizing_mask_options.grid(row=6, column=1, **grid_kwargs)
        self.coordinates_check = BooleanVar(value=config.coordinates)
        self.coordinates_checkbox = ttk.Checkbutton(self.tab3, text='', variable=self.coordinates_check)
        self.coordinates_checkbox.grid(row=0, column=1, **self.grid_checkbox_kwargs)
        self.header_check = BooleanVar(value=config.header)
        self.header_checkbox = ttk.Checkbutton(self.tab3, text='', variable=self.header_check)
        self.header_checkbox.grid(row=1, column=1, **self.grid_checkbox_kwargs)
        self.histogram_check = BooleanVar(value=config.histogram)
        self.histogram_checkbox = ttk.Checkbutton(self.tab3, text='', variable=self.histogram_check)
        self.histogram_checkbox.grid(row=2, column=1, **self.grid_checkbox_kwargs)
        self.cbar_options = ttk.Combobox(self.tab3, values=['', 'vertical', 'horizontal'], state='readonly')
        self.cbar_options.set(['horizontal', 'vertical'][int(config.cbar_vertical)] if config.cbar else '')
        self.cbar_options.grid(row=3, column=1, **grid_kwargs)
        self.fpath_spinbox = ttk.Spinbox(self.tab3, from_=0, to=20)
        self.fpath_spinbox.set(int(config.fpath))
        self.fpath_spinbox.grid(row=4, column=1, **grid_kwargs)
        self.title_entry = ttk.Entry(self.tab3)
        if config.title is not None:
            self.title_entry.insert('0', config.title)
        self.title_entry.grid(row=5, column=1, **grid_kwargs)
        self.fontsize_spinbox = ttk.Spinbox(self.tab3, from_=1, to=200)
        self.fontsize_spinbox.set(config.fontsize)
        self.fontsize_spinbox.grid(row=6, column=1, **grid_kwargs)
        self.cbar_x_spinbox = ttk.Spinbox(self.tab4, from_=0, to=100)
        self.cbar_x_spinbox.set(100 * config.cbar_x)
        self.cbar_x_spinbox.grid(row=0, column=1, **grid_kwargs)
        self.cbar_y_spinbox = ttk.Spinbox(self.tab4, from_=0, to=100)
        self.cbar_y_spinbox.set(100 * config.cbar_y)
        self.cbar_y_spinbox.grid(row=1, column=1, **grid_kwargs)
        self.cbar_width_spinbox = ttk.Spinbox(self.tab4, from_=0, to=100)
        self.cbar_width_spinbox.set(100 * config.cbar_width)
        self.cbar_width_spinbox.grid(row=2, column=1, **grid_kwargs)
        self.cbar_length_spinbox = ttk.Spinbox(self.tab4, from_=0, to=100)
        self.cbar_length_spinbox.set(100 * config.cbar_length)
        self.cbar_length_spinbox.grid(row=3, column=1, **grid_kwargs)
        self.cbar_pad_spinbox = ttk.Spinbox(self.tab4, from_=0, to=500, increment=20)
        self.cbar_pad_spinbox.set(config.cbar_pad)
        self.cbar_pad_spinbox.grid(row=4, column=1, **grid_kwargs)
        self.cbar_label_entry = ttk.Entry(self.tab4)
        if config.cbar_label is not None:
            self.cbar_label_entry.insert('0', config.cbar_label)
        self.cbar_label_entry.grid(row=5, column=1, **grid_kwargs)
        self.cbar_ticks_entry = ttk.Entry(self.tab4)
        if config.cbar_ticks is not None:
            self.cbar_ticks_entry.insert('0', ','.join([str(item) for item in config.cbar_ticks]))
        self.cbar_ticks_entry.grid(row=6, column=1, **grid_kwargs)
        self.tabview.grid(row=0, column=0, sticky='nsew')


class SliderFrame(ttk.Frame):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.grid_rowconfigure(1, weight=1)#, minsize=20)
        self.sliders = {}
        for i, plane in enumerate(PLANES_4D):
            label = ttk.Label(self, text=plane.capitalize())
            label.grid(row=0, column=i, sticky='ns', padx=5, pady=5)
            from_to = (0, 400) if plane == 'time' else (-200, 200)
            slider = ttk.Scale(self, orient='vertical', from_=from_to[1], to=from_to[0], length=50)
            slider.set(0)
            slider.grid(row=1, column=i, sticky='nsew', pady=5)
            self.sliders.update({plane: slider})


class PagesFrame(ttk.Frame):
    def __init__(self, *args, **kwargs):
        config = kwargs.pop('config')
        super().__init__(*args, **kwargs)
        self.grid_columnconfigure((0, 1, 2), weight=1)
        self.previous_button = ttk.Button(self, text='Previous')
        self.previous_button.grid(row=0, column=0, padx=1, sticky='nsew')
        self.page_label = ttk.Label(self, text=f'Page {config.page + 1} of {config.n_pages}')
        self.page_label.grid(row=0, column=1, padx=1, sticky='ns')
        self.next_button = ttk.Button(self, text='Next')
        self.next_button.grid(row=0, column=2, padx=1, sticky='nsew')


class SidebarFrame(ttk.Frame):
    def __init__(self, *args, **kwargs):
        config = kwargs.pop('config')
        toplevel = kwargs.pop('toplevel')
        super().__init__(*args, **kwargs)
        self.grid_rowconfigure(3, weight=1)
        grid_kwargs = {'sticky': 'nsew', 'pady': 1, 'columnspan': 2}
        if not toplevel:
            self.input_frame = InputFrame(self)
            self.input_frame.grid(row=0, **grid_kwargs)
        self.view_button = ttk.Button(self, text='Switch to view 2')
        self.view_button.grid(row=1, sticky=grid_kwargs['sticky'], pady=grid_kwargs['pady'])
        self.clear_mask_button = ttk.Button(self, text='Clear masks')
        self.clear_mask_button.grid(row=1, column=1, sticky=grid_kwargs['sticky'], pady=grid_kwargs['pady'])
        self.options_frame = OptionsFrame(self, config=config)
        self.options_frame.grid(row=2, **grid_kwargs)
        self.sliders_frame = SliderFrame(self)
        self.sliders_frame.grid(row=3, **grid_kwargs)
        if not toplevel:
            self.pages_frame = PagesFrame(self, config=config)
            self.pages_frame.grid(row=4, **grid_kwargs)


class MainFrame(ttk.Frame):
    def __init__(self, *args, **kwargs):
        config = kwargs.pop('config')
        toplevel = kwargs.pop('toplevel')
        self.toplevel = toplevel
        self.config = Config.from_dict(CONFIG_DICT) if config is None else config
        super().__init__(*args, **kwargs)

        self.grid_columnconfigure(0)
        self.grid_columnconfigure(1, weight=1)

        self.image_frame = ttk.Frame(self)
        self.image_frame.grid(row=0, column=1, sticky='nsew')
        self.image_label = ttk.Label(self.image_frame, text='')
        self.image_label.grid(sticky='nsew')

        self.niigrid1 = None
        self.niigrid2 = None
        self.load_niigrid()
        self.image = None
        self.image_grid_boxes = None
        self.image_grid_numbers = None
        self.image_overlay = None
        self.image_origin_coords = None
        self.annotation_buttons = []
        self.update_image(hd=True)

        self.sidebar_frame = SidebarFrame(self, config=self.config, toplevel=toplevel, width=100)
        self.sidebar_frame.grid(row=0, column=0, sticky='nsew')
        self.menu = self.init_menu_bar()

        self.image_label.bind('<Motion>', self.set_image_overlay)
        self.image_label.bind('<Leave>', lambda event: self.set_image_overlay(event, remove_overlay=True))
        self.image_label.bind('<Button-1>', partial(self.update_origin_click, hd=False))
        self.image_label.bind('<B1-Motion>', partial(self.update_origin_click, hd=False))
        self.image_label.bind('<ButtonRelease-1>', partial(self.update_origin_click, hd=True))
        self.master.bind('<space>', lambda e: self.update_image(hd=True))
        self.master.bind('<Button-1>', lambda e: self.update_image(hd=True))
        if not self.toplevel:
            self.set_input_frame()
        self.sidebar_frame.view_button.configure(command=self.set_view)
        self.sidebar_frame.clear_mask_button.configure(command=self.clear_masks)
        self.add_sliders_commands(self.sidebar_frame.sliders_frame.sliders)
        self.set_options_events()
        if not toplevel:
            self.sidebar_frame.pages_frame.previous_button.configure(command=self.set_page)
            self.sidebar_frame.pages_frame.next_button.configure(command=partial(self.set_page, next=True))

    def init_menu_bar(self):
        menu_bar = Menu(self.master)
        # File Menu
        file_menu = Menu(menu_bar, tearoff=0)
        menu_bar.add_cascade(label='Open', menu=file_menu)
        file_menu.add_command(label='Load 3D image...', command=self.open_files)
        self.master.config(menu=menu_bar)
        template_submenu = Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label='...or template', menu=template_submenu)
        for template in TEMPLATES:
            template_submenu.add_command(label=template, command=partial(self.open_files, filepaths=[TEMPLATES[template]], dropdown=True))
        file_menu.add_separator()
        file_menu.add_command(label='Load 3D mask...', command=self.open_files)
        atlas_submenu = Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label='...or atlas', menu=atlas_submenu)
        for atlas in ATLASES:
            atlas_submenu.add_command(label=atlas, command=partial(self.open_files, filepaths=[ATLASES[atlas]], is_mask=True, dropdown=True))
        file_menu.add_separator()
        file_menu.add_command(label='Load configuration', command=self.load_config)
        # Save Menu
        save_menu = Menu(menu_bar, tearoff=0)
        menu_bar.add_cascade(label='Save', menu=save_menu)
        save_image_submenu = Menu(save_menu, tearoff=0)
        save_menu.add_cascade(label='Save image as', menu=save_image_submenu)
        for ftype in FILETYPES:
            save_image_submenu.add_command(label=ftype[1], command=partial(self.save_image, ftype))
        save_menu.add_command(label='Save all images', command=self.save_all_images_or_gifs)
        save_menu.add_command(label='Save GIF', command=self.save_gif)
        save_menu.add_command(label='Save all GIFs', command=lambda: self.save_all_images_or_gifs(gif=True))
        save_menu.add_command(label='Save annotations', command=self.save_annotations)
        save_menu.add_command(label='Save configuration', command=self.save_config)
        # Appearance Menu
        appearance_menu = Menu(menu_bar, tearoff=0)
        menu_bar.add_cascade(label='Appearance', menu=appearance_menu)
        appearance_menu.add_command(label='Dark mode', command=lambda: sv_ttk.set_theme('dark'))
        appearance_menu.add_command(label='Light mode', command=lambda: sv_ttk.set_theme('light'))
        appearance_menu.add_separator()
        tmp_height_submenu = Menu(appearance_menu, tearoff=0)
        appearance_menu.add_cascade(label='Temp. image height', menu=tmp_height_submenu)
        for tmp_height in [None, *TMP_HEIGHTS]:
            label = 'Disable (can be laggy)' if tmp_height is None else tmp_height
            tmp_height_submenu.add_command(label=label, command=partial(self.update_config, attribute='tmp_height', event=tmp_height))
        appearance_menu.add_separator()
        appearance_menu.add_command(label='Fullscreen', command=lambda: self.master.attributes('-fullscreen', not self.master.attributes('-fullscreen')))
        # Extra Options Menu
        extra_options_menu = Menu(menu_bar, tearoff=0)
        menu_bar.add_cascade(label='Extra Options', menu=extra_options_menu)
        extra_options_menu.add_command(label='Annotations', command=self.set_annotation_buttons)
        linewidth_submenu = Menu(extra_options_menu, tearoff=0)
        extra_options_menu.add_cascade(label='Linewidth', menu=linewidth_submenu)
        for linewidth in list(range(1, 9)):
            linewidth_submenu.add_command(label=str(linewidth), command=partial(self.update_config, attribute='linewidth', event=linewidth))
        linecolor_submenu = Menu(extra_options_menu, tearoff=0)
        extra_options_menu.add_cascade(label='Linecolor', menu=linecolor_submenu)
        for linecolor in LINECOLORS:
            linecolor_submenu.add_command(label=linecolor, command=partial(self.update_config, attribute='linecolor', event=linecolor))
        padcolor_submenu = Menu(extra_options_menu, tearoff=0)
        extra_options_menu.add_cascade(label='Padcolor', menu=padcolor_submenu)
        for padcolor in PADCOLORS:
            padcolor_submenu.add_command(label=padcolor, command=partial(self.update_config, attribute='cbar_pad_color', event=padcolor))
        nrows_submenu = Menu(extra_options_menu, tearoff=0)
        extra_options_menu.add_cascade(label='Number of rows', menu=nrows_submenu)
        for nrows in [None] + list(range(1, 9)):
            option = 'Auto' if nrows is None else str(nrows)
            nrows_submenu.add_command(label=option, command=partial(self.update_config, attribute='nrows', event=nrows))
        glass_mode_submenu = Menu(extra_options_menu, tearoff=0)
        extra_options_menu.add_cascade(label='Glassbrain mode', menu=glass_mode_submenu)
        for glass_mode in [None] + list(GLASS_MODES):
            glass_mode_submenu.add_command(label=glass_mode, command=partial(self.update_config, attribute='glass_mode', event=glass_mode))
        coord_sys_submenu = Menu(extra_options_menu, tearoff=0)
        extra_options_menu.add_cascade(label='Coordinate system', menu=coord_sys_submenu)
        for coord_sys in COORDINATE_SYSTEMS:
            coord_sys_submenu.add_command(label=coord_sys, command=partial(self.update_config, attribute='coord_sys', event=coord_sys))
        extra_options_menu.add_command(label='Squeeze', command=partial(self.update_config, attribute='squeeze', switch=True))
        # Help Menu
        menu_bar.add_command(label='Help', command=lambda: open_new_tab(TUTORIAL_URL))
        # About Menu
        about_menu = Menu(menu_bar, tearoff=0)
        menu_bar.add_cascade(label='About', menu=about_menu)
        about_menu.add_command(label='Homepage', command=lambda: open_new_tab(HOMEPAGE_URL))
        about_menu.add_command(label='Author', command=lambda: open_new_tab(AUTHOR_URL))
        about_menu.add_separator()
        about_menu.add_command(label=f'App-Version {__version__}', command=lambda: open_new_tab(RELEASE_URL))
        return menu_bar

    def set_input_frame(self, event=None):
        frame = self.sidebar_frame.input_frame
        frame.image_entry.bind('<Button-1>', lambda e: self.clean_entry(frame.image_entry))
        frame.image_entry.bind('<FocusOut>', lambda e: self.placehold_entry(frame.image_entry))
        frame.image_entry.bind('<Return>', lambda e: self.open_files(filepaths=frame.image_entry.get()))
        frame.image_entry.dnd_bind('<<Drop>>', self.open_files)
        frame.mask_entry.bind('<Button-1>', lambda e:self.clean_entry(frame.mask_entry, is_mask=True))
        frame.mask_entry.bind('<FocusOut>', lambda e: self.placehold_entry(frame.mask_entry, is_mask=True))
        frame.mask_entry.bind('<Return>', lambda e: self.open_files(filepaths=frame.mask_entry.get(), is_mask=True))
        frame.mask_entry.bind(f'<{CMD_KEY}-n>', lambda e: self.convert_dicom_and_open(input_filepath=frame.image_entry.get(),
                                                                                      output_dirpath=frame.mask_entry.get()))
        frame.mask_entry.dnd_bind('<<Drop>>', partial(self.open_files, is_mask=True))

    def set_options_events(self):
        frame = self.sidebar_frame.options_frame
        # TAB: MAIN
        frame.height_spinbox.config(command=lambda: self.set_height(int(frame.height_spinbox.get())))
        frame.height_spinbox.bind('<Return>', lambda e: self.set_height(int(frame.height_spinbox.get())))
        frame.layout_options.bind('<<ComboboxSelected>>', lambda e: self.update_config('layout', frame.layout_options.get()))
        frame.layout_options.bind('<Return>', lambda e: self.update_config('layout', frame.layout_options.get()))
        frame.cmap_options.bind('<<ComboboxSelected>>', lambda e: self.set_cmap(frame.cmap_options.get()))
        frame.cmap_options.bind('<Return>', lambda e: self.set_cmap(frame.cmap_options.get()))
        frame.cmap_mask_options.bind('<<ComboboxSelected>>', lambda e: self.set_cmap(frame.cmap_mask_options.get(), is_mask=True))
        frame.cmap_mask_options.bind('<Return>', lambda e: self.set_cmap(frame.cmap_mask_options.get(), is_mask=True))
        frame.alpha_spinbox.config(command=lambda: self.update_config('alpha', float(frame.alpha_spinbox.get()) / 100))
        frame.alpha_spinbox.bind('<Return>', lambda e: self.update_config('alpha', float(frame.alpha_spinbox.get()) / 100))
        frame.max_samples_spinbox.config(command=lambda: self.set_max_samples(int(frame.max_samples_spinbox.get())))
        frame.max_samples_spinbox.bind('<Return>', lambda e: self.set_max_samples(int(frame.max_samples_spinbox.get())))
        frame.crosshair_checkbox.config(command=lambda: self.update_config('crosshair', switch=True))
        # TAB: IMAGE
        frame.equal_hist_checkbox.config(command=partial(self.update_config, attribute='equal_hist', event=frame.equal_hist_check, switch=True))
        frame.qrange_start_spinbox.config(command=lambda: self.set_quantile_range(float(frame.qrange_start_spinbox.get())))
        frame.qrange_start_spinbox.bind('<Return>', lambda e: self.set_quantile_range(float(frame.qrange_start_spinbox.get())))
        frame.qrange_stop_spinbox.config(command=lambda: self.set_quantile_range(float(frame.qrange_stop_spinbox.get()), stop=True))
        frame.qrange_stop_spinbox.bind('<Return>', lambda e: self.set_quantile_range(float(frame.qrange_stop_spinbox.get()), stop=True))
        frame.vrange_start_spinbox.config(command=lambda: self.set_value_range(float(frame.vrange_start_spinbox.get())))
        frame.vrange_start_spinbox.bind('<Return>', lambda e: self.set_value_range(float(frame.vrange_start_spinbox.get())))
        frame.vrange_stop_spinbox.config(command=lambda: self.set_value_range(float(frame.vrange_stop_spinbox.get()), stop=True))
        frame.vrange_stop_spinbox.bind('<Return>', lambda e: self.set_value_range(float(frame.vrange_stop_spinbox.get()), stop=True))
        frame.transp_if_entry.bind('<Return>', self.set_transp_if)
        frame.resizing_options.bind('<<ComboboxSelected>>', lambda e: self.update_config('resizing', RESIZINGS.index(frame.resizing_options.get())))
        frame.resizing_options.bind('<Return>', lambda e: self.update_config('resizing', RESIZINGS.index(frame.resizing_options.get())))
        # TAB: MASK
        frame.qrange_start_mask_spinbox.config(command=lambda: self.set_quantile_range(float(frame.qrange_start_mask_spinbox.get()), is_mask=True))
        frame.qrange_start_mask_spinbox.bind('<Return>', lambda e: self.set_quantile_range(float(frame.qrange_start_mask_spinbox.get()), is_mask=True))
        frame.qrange_stop_mask_spinbox.config(command=lambda: self.set_quantile_range(float(frame.qrange_stop_mask_spinbox.get()), stop=True, is_mask=True))
        frame.qrange_stop_mask_spinbox.bind('<Return>', lambda e: self.set_quantile_range(float(frame.qrange_stop_mask_spinbox.get()), stop=True, is_mask=True))
        frame.vrange_start_mask_spinbox.config(command=lambda: self.set_value_range(float(frame.vrange_start_mask_spinbox.get()), is_mask=True))
        frame.vrange_start_mask_spinbox.bind('<Return>', lambda e: self.set_value_range(float(frame.vrange_start_mask_spinbox.get()), is_mask=True))
        frame.vrange_stop_mask_spinbox.config(command=lambda: self.set_value_range(float(frame.vrange_stop_mask_spinbox.get()), stop=True, is_mask=True))
        frame.vrange_stop_mask_spinbox.bind('<Return>', lambda e: self.set_value_range(float(frame.vrange_stop_mask_spinbox.get()), stop=True, is_mask=True))
        frame.transp_if_mask_entry.bind('<Return>', lambda e: self.set_transp_if(is_mask=True))
        frame.resizing_mask_options.bind('<<ComboboxSelected>>', lambda e: self.update_config('resizing', RESIZINGS.index(frame.resizing_mask_options.get()), is_mask=True))
        frame.resizing_mask_options.bind('<Return>', lambda e: self.update_config('resizing', RESIZINGS.index(frame.resizing_mask_options.get()), is_mask=True))
        frame.is_atlas_checkbox.config(command=self.set_is_atlas)
        # TAB: OVERLAY
        frame.coordinates_checkbox.config(command=lambda: self.update_config('coordinates', switch=True))
        frame.header_checkbox.config(command=lambda: self.update_config('header', switch=True))
        frame.histogram_checkbox.config(command=lambda: self.update_config('histogram', switch=True))
        frame.cbar_options.bind('<<ComboboxSelected>>', lambda e: self.set_cbar(frame.cbar_options.get()))
        frame.fpath_spinbox.config(command=lambda: self.update_config('fpath', int(frame.fpath_spinbox.get())))
        frame.fpath_spinbox.bind('<Return>', lambda e: self.update_config('fpath', int(frame.fpath_spinbox.get())))
        frame.title_entry.bind('<Return>', lambda e: self.set_title(frame.title_entry.get()))
        frame.fontsize_spinbox.config(command=lambda: self.update_config('fontsize', int(frame.fontsize_spinbox.get())))
        frame.fontsize_spinbox.bind('<Return>', lambda e: self.update_config('fontsize', int(frame.fontsize_spinbox.get())))
        # TAB: COLORBAR
        frame.cbar_x_spinbox.config(command=lambda: self.update_config('cbar_x', float(frame.cbar_x_spinbox.get()) / 100))
        frame.cbar_x_spinbox.bind('<Return>', lambda e: self.update_config('cbar_x', float(frame.cbar_x_spinbox.get()) / 100))
        frame.cbar_y_spinbox.config(command=lambda: self.update_config('cbar_y', float(frame.cbar_y_spinbox.get()) / 100))
        frame.cbar_y_spinbox.bind('<Return>', lambda e: self.update_config('cbar_y', float(frame.cbar_y_spinbox.get()) / 100))
        frame.cbar_width_spinbox.config(command=lambda: self.update_config('cbar_width', float(frame.cbar_width_spinbox.get()) / 100))
        frame.cbar_width_spinbox.bind('<Return>', lambda e: self.update_config('cbar_width', float(frame.cbar_width_spinbox.get()) / 100))
        frame.cbar_length_spinbox.config(command=lambda: self.update_config('cbar_length', float(frame.cbar_length_spinbox.get()) / 100))
        frame.cbar_length_spinbox.bind('<Return>', lambda e: self.update_config('cbar_length', float(frame.cbar_length_spinbox.get()) / 100))
        frame.cbar_pad_spinbox.config(command=lambda: self.update_config('cbar_pad', int(frame.cbar_pad_spinbox.get())))
        frame.cbar_pad_spinbox.bind('<Return>', lambda e: self.update_config('cbar_pad', int(frame.cbar_pad_spinbox.get())))
        frame.cbar_label_entry.bind('<Return>', lambda e: self.update_config('cbar_label', frame.cbar_label_entry.get()))
        frame.cbar_ticks_entry.bind('<Return>', self.set_cbar_ticks)

    @property
    def niigrid(self):
        return [self.niigrid1, self.niigrid2][self.config.view - 1]

    def load_niigrid(self):
        setattr(self, f'niigrid{self.config.view}', NiftiImageGrid(self.config.get_filepaths()))
        other_view = {1: 2, 2: 1}[self.config.view]
        if getattr(self, f'niigrid{other_view}') is not None:
            setattr(self, f'niigrid{other_view}', NiftiImageGrid(self.config.get_filepaths(view=other_view)))

    def clean_entry(self, entry, is_mask=False):
        prefix = 'mask' if is_mask else 'image'
        if entry.get() == PATH_PLACEHOLDER[prefix]:
            entry.delete(0, 'end')

    def placehold_entry(self, entry, is_mask=False):
        prefix = 'mask' if is_mask else 'image'
        if entry.get() == '':
            entry.insert(0, PATH_PLACEHOLDER[prefix])

    def set_view(self, event=None):
        self.sidebar_frame.view_button.configure(text=f'Switch to view {self.config.view}')
        self.config.view = 2 if self.config.view == 1 else 1
        if getattr(self, f'niigrid{self.config.view}') is None:
            self.load_niigrid()
        self.update_image()

    def clear_masks(self):
        self.config.remove_mask_layers()
        self.load_niigrid()
        self.update_image()

    def add_sliders_commands(self, sliders):
        for i, plane in enumerate(PLANES_4D):
            sliders[plane].bind('<Button-4>', partial(self.update_origin_scroll, plane=plane))
            sliders[plane].bind('<Button-5>', partial(self.update_origin_scroll, plane=plane, scroll_up=False))
            sliders[plane].bind('<Button-1>', lambda e: self.update_origin(hd=False))
            sliders[plane].bind('<B1-Motion>', lambda e: self.update_origin(hd=False))
            sliders[plane].bind('<ButtonRelease-1>', lambda e: self.update_origin(hd=True))

    def set_max_samples(self, max_samples):
        self.config.set_max_samples(max_samples)
        self.load_niigrid()
        self.update_image()
        self.focus_set()

    def set_annotation_buttons(self):
        self.config.annotations = not self.config.annotations
        if len(self.annotation_buttons) > 0:
            self.destroy_annotation_buttons()
        else:
            self.create_annotation_buttons()

    def destroy_annotation_buttons(self):
        if len(self.annotation_buttons) > 0:
            for i in range(len(self.annotation_buttons)):
                self.annotation_buttons[i].destroy()
            self.annotation_buttons = []

    def create_annotation_buttons(self, annotations_=('0', '1', '2')):
        self.annotation_buttons = []
        for nimage, box in zip(self.niigrid1.niis, self.image_grid_boxes):
            button = ttk.Combobox(self.image_frame, values=annotations_)
            button.bind('<<ComboboxSelected>>', partial(self.set_annotation, filepath=nimage.nics[0].filepath))
            button.bind('<Return>', partial(self.set_annotation, filepath=nimage.nics[0].filepath))
            button.set(self.config.annotation_dict[nimage.nics[0].filepath])
            button.place(x=box[2], y=box[1], anchor='ne')
            self.annotation_buttons.append(button)

    def set_annotation(self, event, filepath):
        self.config.annotation_dict.update({filepath: event.widget.get()})

    def set_cmap(self, event, is_mask=False):
        if event == 'CATALOG':
            open_new_tab('https://cmap-docs.readthedocs.io/en/latest/catalog/')
        else:
            self.update_config('cmap', event, is_mask)

    def set_height(self, height):
        if self.master.is_fullscreen:
            self.update_config('height', height)
        else:
            width = self.image.size[0] * height / self.image.size[1] + self.sidebar_frame.winfo_width()
            self.master.geometry(f'{int(width) + 1}x{height + self.menu.winfo_height() + 1}')
            self.focus_set()

    def set_title(self, title):
        self.config.set_title(title)
        self.update_image()
        self.focus_set()

    def unset_title(self):
        self.sidebar_frame.options_frame.title_entry.delete(0, 'end')
        self.config.set_title('')
        self.update_image()
        self.focus_set()

    def set_equal_hist(self, event=None):
        self.sidebar_frame.options_frame.equal_hist_check.set(not self.config.equal_hist)
        self.update_config('equal_hist', switch=True)

    def set_transp_if(self, event=None, is_mask=False):
        substr = '_mask' if is_mask else ''
        transp_if = getattr(self.sidebar_frame.options_frame, f'transp_if{substr}_entry').get()
        transp_if = None if transp_if == '' else transp_if
        self.update_config('transp_if', transp_if, is_mask=is_mask)

    def set_quantile_range(self, event, is_mask=False, stop=False, increment=None):
        if self.config.qrange[-1 if is_mask else 0] is None:
            qrange = list(QRANGE[int(is_mask)])
        else:
            qrange = list(self.config.qrange[-1 if is_mask else 0])
        qrange[int(stop)] = event / 100 if increment is None else qrange[int(stop)] + increment / 100
        qrange[int(stop)] = min(max(0, qrange[int(stop)]), 1)
        self.update_config('qrange', qrange, is_mask)
        value_range = self.niigrid.niis[0].cmaps[-1 if is_mask else 0].vrange
        self.config.set_layer_attribute('vrange', None, is_mask)  # Setting vrange to None such that qrange has effect
        if is_mask:
            self.sidebar_frame.options_frame.vrange_start_mask_spinbox.set(value_range[0])
            self.sidebar_frame.options_frame.vrange_stop_mask_spinbox.set(value_range[-1])
            if increment is not None:
                self.sidebar_frame.options_frame.qrange_start_mask_spinbox.set(qrange[0] * 100)
                self.sidebar_frame.options_frame.qrange_stop_mask_spinbox.set(qrange[1] * 100)
        else:
            self.sidebar_frame.options_frame.vrange_start_spinbox.set(value_range[0])
            self.sidebar_frame.options_frame.vrange_stop_spinbox.set(value_range[-1])
            if increment is not None:
                self.sidebar_frame.options_frame.qrange_start_spinbox.set(qrange[0] * 100)
                self.sidebar_frame.options_frame.qrange_stop_spinbox.set(qrange[1] * 100)

    def set_value_range(self, event, is_mask=False, stop=False):
        vrange = self.niigrid.niis[0].cmaps[-1 if is_mask else 0].vrange
        vrange[-1 if stop else 0] = event
        self.update_config('vrange', vrange, is_mask)

    def set_is_atlas(self):
        is_atlas = self.config.is_atlas
        self.update_config('is_atlas', not is_atlas[-1], is_mask=True)

    def set_cbar(self, event):
        self.config.cbar_vertical = event == 'vertical'
        self.update_config('cbar', event != '')

    def set_cbar_ticks(self, event):
        self.config.set_cbar_ticks(event.widget.get())
        self.update_image()
        self.focus_set()

    def set_page(self, next=False):
        page = self.config.page + 1 if next else self.config.page - 1
        if page in list(range(self.config.n_pages)):
            self.config.page = page
            self.load_niigrid()
            self.update_image()
            self.sidebar_frame.pages_frame.page_label.configure(text=f'Page {page + 1} of {self.config.n_pages}')
            if self.config.annotations:
                self.destroy_annotation_buttons()
                self.create_annotation_buttons()


    def update_config(self, attribute, event=None, is_mask=False, switch=False):
        if attribute in LAYER_ATTRIBUTES:
            self.config.set_layer_attribute(attribute, event, is_mask)
        else:
            setattr(self.config, attribute, not getattr(self.config, attribute) if switch else event)
        self.update_image()
        self.focus_set()

    def convert_dicom_and_open(self, input_filepath=None, output_dirpath=None):
        filepaths = dcm2nii(input_filepath, output_dirpath)
        if len(filepaths) > 0:
            image_path, mask_path = f'{output_dirpath}/*.ni*', ''
            self.sidebar_frame.input_frame.image_entry.insert('0', image_path)
            self.sidebar_frame.input_frame.image_entry.delete(len(image_path), 'end')
            self.sidebar_frame.input_frame.mask_entry.insert('0', mask_path)
            self.sidebar_frame.input_frame.mask_entry.delete(len(mask_path), 'end')
            self.open_files(filepaths=filepaths)

    def open_files(self, event=None, filepaths=None, is_mask=False, title='Open Nifti Files', dropdown=False):
        if filepaths is None:
            if isinstance(event, TkinterDnD.DnDEvent):
                filepaths = parse_dnd_filepaths(event.data)
            else:
                filepaths = filedialog.askopenfilenames(title=title, filetypes=[('All Files', '*.*')])
        if filepaths:
            self.unset_title()
            self.config.add_filepaths(filepaths, is_mask)
            self.load_niigrid()
            self.update_image()
            self.focus_set()

    def remove_mask_layers(self):
        self.config.remove_mask_layers()
        setattr(self, f'niigrid{self.config.view}', NiftiImageGrid(self.config.get_filepaths()))
        self.update_image()

    def update_origin_click(self, event, hd=True):
        if 0 <= event.x < self.image.size[0] and 0 <= event.y < self.image.size[1]:
            for plane, v in zip(PLANES, self.image_origin_coords[event.x, event.y]):
                if not np.isnan(v):
                    self.sidebar_frame.sliders_frame.sliders[plane].set(v)
            self.update_origin(hd)

    def update_origin_scroll(self, event=None, plane=None, scroll_up=True, scroll_speed=1, hd=True):
        if (not isinstance(self.focus_displayof(), (ttk.Spinbox, ttk.Entry, ttk.Combobox))) and event.type == EventType.KeyPress:
            value = self.config.origin[PLANES_4D.index(plane)] + (1 if scroll_up else -1) * scroll_speed
            self.sidebar_frame.sliders_frame.sliders[plane].set(value)
            self.update_origin(hd)

    def update_origin(self, hd=True):
        self.config.origin = [self.sidebar_frame.sliders_frame.sliders[p].get() for p in PLANES_4D]
        self.update_image(hd)

    def update_image(self, hd=True):
        self.image = self.get_image(hd)
        self.update_overlay_and_annotations()
        tk_image = ImageTk.PhotoImage(self.image)
        self.image_label.config(image=tk_image)
        self.image_label.image = tk_image
        if hasattr(self, 'sidebar_frame'):
            self.update_sidebar()

    def get_image(self, hd=True):
        config_dict = self.config.to_dict(grid_kwargs_only=True, hd=hd)
        return self.niigrid.get_image(**config_dict)

    def update_overlay_and_annotations(self):
        updated_grid_boxes = self.niigrid.boxes
        if self.image_grid_boxes is None or updated_grid_boxes != self.image_grid_boxes:
            self.image_grid_boxes = updated_grid_boxes
            self.image_grid_numbers = self.get_grid_numbers()
            self.image_origin_coords = self.get_origin_coordinates()
            if self.config.annotations:
                self.destroy_annotation_buttons()
                self.create_annotation_buttons()

    def update_sidebar(self):
        if hasattr(self.sidebar_frame.options_frame, 'tabview'):
            frame = self.sidebar_frame
            nimage = self.niigrid.niis[0]
            frame.options_frame.vrange_start_spinbox.set(nimage.cmaps[0].vrange[0])
            frame.options_frame.vrange_stop_spinbox.set(nimage.cmaps[0].vrange[-1])
            frame.options_frame.resizing_options.set(RESIZINGS[self.config.resizing[0]])
            frame.options_frame.resizing_mask_options.set(RESIZINGS[self.config.resizing[-1]])
            if self.config.n_layers > 1:
                frame.options_frame.vrange_start_mask_spinbox.set(nimage.cmaps[-1].vrange[0])
                frame.options_frame.vrange_stop_mask_spinbox.set(nimage.cmaps[-1].vrange[-1])
        if hasattr(self.sidebar_frame, 'pages_frame'):
            page = min(self.config.page, self.config.n_pages - 1)
            self.sidebar_frame.pages_frame.page_label.configure(text=f'Page {page + 1} of {self.config.n_pages}')

    def set_image_overlay(self, event, remove_overlay=False):
        tk_image = ImageTk.PhotoImage(self.image, size=self.image.size)
        if not remove_overlay and 0 <= event.x < self.image.size[0] and 0 <= event.y < self.image.size[1]:
            box_number = self.image_grid_numbers[event.x, event.y]
            if 0 <= box_number < len(self.image_grid_boxes) and len(self.image_grid_boxes) > 1:
                box = self.image_grid_boxes[box_number]
                box_frame = Image.fromarray(get_window_frame(size=(box[2] - box[0], box[3] - box[1])))
                alpha = Image.new('L', self.image.size, 255)
                alpha.paste(box_frame, self.image_grid_boxes[box_number])
                im = Image.composite(self.image, Image.new(self.image.mode, self.image.size, 'white'), alpha)
                tk_image = ImageTk.PhotoImage(im, size=self.image.size)
        self.image_label.configure(image=tk_image)
        self.image_label.image = tk_image

    def get_grid_numbers(self):
        numbers = -np.ones(self.image.size, dtype=np.int16)
        for i, box in enumerate(self.image_grid_boxes):
            numbers[box[0]:box[2], box[1]:box[3]] = i
        return numbers

    def get_origin_coordinates(self):
        coords = np.zeros((*self.image.size, 3), dtype=np.float32)
        for nii, grid_box in zip(self.niigrid.niis, self.niigrid.boxes):
            bounds = nii.nics[0].get_origin_bounds(self.config.coord_sys)
            for i, kw in enumerate(nii.nics[0]._image_props):
                size = kw['size']
                dim = PLANES.index(kw['plane'])
                x, y = [ii for ii in range(3) if ii != dim]
                box_coords = np.meshgrid(*[np.linspace(bounds[0, x], bounds[1, x], size[0]),
                                           np.linspace(bounds[1, y], bounds[0, y], size[1])], indexing='ij', copy=False)
                box_coords = np.stack(box_coords, axis=-1)
                box_coords = np.insert(box_coords, dim, np.nan, axis=-1)
                box = grid_box[0] + kw['box'][0], grid_box[1] + kw['box'][1]
                coords[box[0]:box[0] + size[0], box[1]:box[1] + size[1]] = box_coords
        return coords

    def save_image(self, filetype):
        extension = filetype[1].split(';')[0][1:]
        filepath = filedialog.asksaveasfilename(defaultextension=extension, filetypes=[filetype])
        if filepath:
            config_dict = self.config.to_dict(grid_kwargs_only=True, hd=True)
            if extension in ['.png', '.jpg', '.jpeg', '.tif', '.tiff']:
                image = self.niigrid.get_image(**config_dict)
                image.save(filepath)
            else:
                self.niigrid.save_image(filepath, **config_dict)

    def save_gif(self):
        filepath = filedialog.asksaveasfilename(defaultextension='.gif',
                                                filetypes=[('Graphics Interchange Format', '*.gif')])
        if filepath:
            config_dict = self.config.to_dict(grid_kwargs_only=True, hd=True)
            save_gif(self.niigrid, filepath, duration=50, loop=0, start=None, stop=None, **config_dict)

    def save_all_images_or_gifs(self, gif=False):
        dirpath = filedialog.askdirectory()
        if dirpath:
            config_dict = self.config.to_dict(grid_kwargs_only=True, hd=True)
            save_images_or_gifs(self.config.filepaths, dirpath, gif, self.config.max_samples, **config_dict)

    def save_config(self):
        filepath = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('JSON Files', '.json')])
        if filepath:
            self.config.save(filepath)

    def load_config(self):
        filepath = filedialog.askopenfilename(title='Open Config File', filetypes=[('JSON Files', '.json')])
        if filepath:
           self.config = Config.from_json(filepath)
           self.load_niigrid()
           self.update_image()

    def save_annotations(self):
        filepath = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('Comma-separated values', '.csv')])
        if filepath:
            self.config.save_annotations(filepath)


class ToplevelWindow(Toplevel):
    def __init__(self, *args, **kwargs):
        config = kwargs.pop('config')
        super().__init__(*args, **kwargs)
        self.title('NiftiView')
        set_icon(self)
        self.is_fullscreen = False
        self.mainframe = MainFrame(self, config=config, toplevel=True)
        self.mainframe.pack(anchor='nw', fill='both', expand=True)
        add_key_bindings(self)


class NiftiView(Tk):
    def __init__(self, config=None):
        super().__init__()
        self.title('NiftiView')
        set_icon(self)
        sv_ttk.set_theme(config.appearance_mode)
        self.is_fullscreen = False
        self.mainframe = MainFrame(self, config=config, toplevel=False)
        self.mainframe.pack(anchor='nw', fill='both', expand=True)
        self.toplevel_window = None
        self.mainframe.image_label.bind('<Double-Button-1>', self.set_toplevel_window)
        self.bind(f'<{CMD_KEY}-BackSpace>', lambda e: self.mainframe.set_page(next=False))
        self.bind(f'<Button-3>', lambda e: self.mainframe.set_page(next=True))
        add_key_bindings(self)

    def set_toplevel_window(self, event):
        if self.toplevel_window is not None:
            self.toplevel_window.destroy()
        if 0 <= event.x < self.mainframe.image.size[0] and 0 <= event.y < self.mainframe.image.size[1]:
            window_number = self.mainframe.image_grid_numbers[event.x, event.y]
            config = deepcopy(self.mainframe.config)
            fpaths = config.get_filepaths()
            if 0 <= window_number < len(fpaths):
                setattr(config, f'filepaths_view{config.view}', [fpaths[window_number]])
                self.toplevel_window = ToplevelWindow(self, config=config)


def add_key_bindings(app):
    app.bind(f'<{CMD_KEY}-a>', lambda e: app.mainframe.set_quantile_range(None, increment=-5))
    app.bind(f'<{CMD_KEY}-d>', lambda e: app.mainframe.set_quantile_range(None, increment=5))
    app.bind(f'<{CMD_KEY}-s>', lambda e: app.mainframe.set_quantile_range(None, increment=-1, stop=True))
    app.bind(f'<{CMD_KEY}-w>', lambda e: app.mainframe.set_quantile_range(None, increment=1, stop=True))
    app.bind(f'<{CMD_KEY}-Return>', lambda e: app.mainframe.set_equal_hist())
    app.bind('<Escape>', lambda e: app.wm_attributes('-fullscreen', False))
    app.bind('<Configure>', debounce(app, partial(resize_window, app)))
    app.bind(f'<{CMD_KEY}-space>', lambda e: app.mainframe.update_config('alpha', 0.))
    app.bind(f'<{CMD_KEY}-KeyRelease-space>', lambda e: app.mainframe.update_config('alpha', float(app.mainframe.sidebar_frame.options_frame.alpha_spinbox.get()) / 100))
    for plane, keys in zip(PLANES_4D, [('Left', 'Right'), (f'{CMD_KEY}-Left', f'{CMD_KEY}-Right'), ('Down', 'Up'), (f'{CMD_KEY}-Down', f'{CMD_KEY}-Up')]):
        app.bind(f'<{keys[0]}>', partial(app.mainframe.update_origin_scroll, plane=plane, scroll_up=False, hd=False))
        app.bind(f'<{keys[1]}>', partial(app.mainframe.update_origin_scroll, plane=plane, hd=False))
        #app.bind(f'<KeyRelease-{keys[0]}>', partial(app.mainframe.update_origin_scroll, plane=plane, scroll_up=False))
        #app.bind(f'<KeyRelease-{keys[1]}>', partial(app.mainframe.update_origin_scroll, plane=plane))


def resize_window(app, *args):
    if str(args[0]._w) in ['.', '.!toplevelwindow']:
        if not app.is_fullscreen:
            size = [app.mainframe.winfo_width() - app.mainframe.sidebar_frame.winfo_width(), app.mainframe.winfo_height()]
            ratio = size[0] / size[1]
            size = [int(round(size[0])), int(round(size[1]))]
            image_ratio = app.mainframe.image.size[0] / app.mainframe.image.size[1]
            height = int(size[1] if ratio >= image_ratio else size[0] / image_ratio)
            if height > 0 and abs(height - app.mainframe.image.size[1]) > 1:
                app.mainframe.config.height = int(height)
                app.mainframe.update_image(hd=False)
                app.mainframe.sidebar_frame.options_frame.height_spinbox.set(height)
                #app.after(30, app.mainframe.update_image(hd=True))
        app.is_fullscreen = window_is_fullscreen_or_maximized(app)


def window_is_fullscreen_or_maximized(app):
    return app.attributes('-fullscreen') or app.winfo_height() > app.winfo_screenheight() - 100


def set_icon(app):
    app.iconpath = ImageTk.PhotoImage(file=f'{DATA_PATH}/niftiview.ico')
    #app.wm_iconbitmap()
    app.iconphoto(False, app.iconpath)


def main(filepaths=None):
    config = Config.from_dict(CONFIG_DICT)
    if len(argv) > 1:
        config.add_filepaths(filepaths)
    app = NiftiView(config)
    app.mainloop()


if __name__ == '__main__':
    main(filepaths=argv[1:] if len(argv) > 1 else None)
