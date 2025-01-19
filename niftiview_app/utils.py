import re
import glob
import warnings
import numpy as np
import importlib.resources
from pathlib import Path

from niftiview.utils import load_json
DATA_PATH = str(importlib.resources.files('niftiview_app')) + '/data'
CONFIG_DICT = load_json(f'{DATA_PATH}/config.json')


def parse_dnd_filepaths(filepaths):
    return [fp.strip('{}') for fp in re.findall(r'{[^}]*}|\S+', filepaths)]


def get_window_frame(size, exp=12):
    x, y = np.meshgrid(np.linspace(-1, 1, size[0]), np.linspace(-1, 1, size[1]), indexing='xy', copy=False)
    frame = (x ** exp + y ** exp) / 2
    return (255 * (1 - frame)).astype(np.uint8)


def dcm2nii(input_filepath=None, output_dirpath=None):
    import dcm2niix
    if Path(input_filepath).is_dir() or (Path(input_filepath).is_file() and input_filepath.endswith('.dcm')):
        if Path(output_dirpath).is_dir():
            dcm2niix.main(['-o',  output_dirpath, input_filepath])
        else:
            warnings.warn(f'{output_dirpath} is not an existing directory')
    else:
        warnings.warn(f'{input_filepath} is not a dicom file')
    return sorted(glob.glob(f'{output_dirpath}/*.ni*'))


def debounce(app, func, wait=1):
    def debounced(event):
        def call_it():
            func(app)
            debounced._timer = None
        if debounced._timer:
            app.after_cancel(debounced._timer)
        debounced._timer = app.after(wait, call_it)
    debounced._timer = None
    return debounced
