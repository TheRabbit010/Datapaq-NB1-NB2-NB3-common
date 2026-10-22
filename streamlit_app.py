import io
import os
import re
import struct
import zlib
import math
import numpy as np
import olefile
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import streamlit as st
import statistics
from PIL import Image
from datetime import datetime, time, timedelta

# ==============================================================================
# STREAMLIT PAGE CONFIGURATION & CSS STYLING
# ==============================================================================
st.set_page_config(page_title="Datapaq .PAQ Analyzer & Furnace Profiler", page_icon="🔥", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
div[data-testid="stMetricValue"] { font-size: 1.8rem !important; font-weight: 700 !important; white-space: normal !important; line-height: 1.2 !important; }
div[data-testid="stMetricLabel"] { font-size: 1.1rem !important; font-weight: 500 !important; color: #a0aab2 !important; }
div.stButton > button:first-child { background-color: #ff4b4b; color: white; font-weight: bold; border-radius: 5px; width: 100%; margin-bottom: 20px; }
div.stButton > button:first-child:hover { background-color: #ff3333; border-color: #ff3333; }
button[data-baseweb="tab"] { font-size: 1.35rem !important; font-weight: 700 !important; padding: 1rem 1.5rem !important; }
div[data-testid="stAlert"] { font-size: 1.15rem !important; font-weight: 500 !important; padding: 1rem !important; }
.custom-info-box { background-color: rgba(33, 150, 243, 0.1); border-left: 5px solid #2196F3; padding: 15px; border-radius: 5px; margin-bottom: 15px; font-size: 1.05rem; }
.custom-warning-box { background-color: rgba(255, 252, 230, 1.0); border-left: 5px solid #f39c12; padding: 20px; border-radius: 5px; margin-bottom: 15px; font-size: 1.15rem; color: #8a6d3b; }
@media (prefers-color-scheme: dark) { .custom-warning-box { background-color: rgba(255, 152, 0, 0.15); color: #f39c12; } }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# DATAPAQ GLOBAL CONSTANTS
# ==============================================================================
PROBE_COLORS = {"PB#1": "#ff0000", "PB#2": "#00ff00", "PB#3": "#0000ff", "PB#4": "#8b4513", "PB#5": "#ff00ff", "PB#6": "#b8860b", "PB#7": "#800080", "PB#8": "#00ffff", "PB#9": "#d32f2f", "PB#10": "#5c4033"}
GROUP_COLORS = {"Dryer": "rgba(255, 235, 156, 0.15)", "Debinder": "rgba(255, 199, 119, 0.15)", "Heating": "rgba(255, 160, 160, 0.15)", "Cooling": "rgba(173, 216, 230, 0.15)"}

STANDARD_SPECS = {
    "NB1 (RAD)": {"id": "PRCNVR02044 Rev C", "max": "Dryer: 175-260°C &nbsp;|&nbsp; Debinder: 200-375°C &nbsp;|&nbsp; Brazing: 583-607°C", "dwell": "Dryer ≥175°C ≥ 1.00 min &nbsp;|&nbsp; Debinder ≥200°C ≥ 2.00 min &nbsp;|&nbsp; Brazing ≥577°C = 2.30 - 7.00 min, ≥583°C ≥ 2.30 min"},
    "NB1 (CDS/KN9/12SHP)": {"id": "PRCNVR02004 Rev.E + 2025 DSR TDOC_101182039 CDS BRAZING CYCLE", "max": "Dryer: 200-350°C &nbsp;|&nbsp; Debinder: 300-375°C &nbsp;|&nbsp; Brazing: 585-607°C", "dwell": "Dryer ≥200°C ≥ 1.30 min &nbsp;|&nbsp; Debinder ≥300°C ≥ 2.30 min &nbsp;|&nbsp; Brazing ≥577°C = 4.00 - 7.45 min (PB#1, PB#5) / 2.00 - 7.45 min (Others)"},
    "NB3 (KE8 : M2/EVO)": {"id": "PRCNVR02059 + V-PAS/T88/Chon Buri 1/2025-10-29-ZVK (Evaporator M2 ,EVO)", "max": "Dryer: 200-375°C &nbsp;|&nbsp; Brazing: M2 = 595-602°C , EVO = 598-606°C", "dwell": "Dryer ≥200°C ≥ 1.30 min &nbsp;|&nbsp; Brazing ≥550°C = 7.00 - 10.30 min, ≥577°C = 4.30 - 7.00 min, ≥591°C = 1.30 - 4.00 min"},
    "NB2 (Tahc)": {"id": "PRCNVR02050 Rev B", "max": "Dryer: 200-375°C &nbsp;|&nbsp; Brazing: 596-604°C", "dwell": "Dryer ≥250°C ≥ 1.00 min &nbsp;|&nbsp; Brazing ≥577°C = 4.00 - 7.00 min, ≥591°C = 1.30 - 4.30 min"},
    "NB2 (Utahc)": {"id": "PRCNVR02050 Rev B + internal control", "max": "Dryer: 200-375°C &nbsp;|&nbsp; Brazing: 596-606°C", "dwell": "Dryer ≥250°C ≥ 1.00 min &nbsp;|&nbsp; Brazing ≥577°C = 4.00 - 7.00 min, ≥591°C = 1.30 - 4.30 min"},
    "NB3 (BTM)": {"id": "PRCNVR02033 Rev C", "max": "Dryer: 300-375°C &nbsp;|&nbsp; Brazing: 595-608°C", "dwell": "Dryer ≥300°C ≥ 2.00 min &nbsp;|&nbsp; Brazing ≥577°C = 4.00 - 14.00 min, ≥591°C = 2.00 - 12.00 min, ≥600°C ≤ 8.00 min"}
}

VALIDATION_RULES = {
    "NB1 (RAD)": {"Dryer Max (°C)": (175, 260), "Debinder Max (°C)": (200, 375), "Brazing Max (°C)": (583, 607), "Dryer Dwell (≥175°C)": (60, 99999), "Debinder Dwell (≥200°C)": (120, 99999), "Brazing Dwell (≥577°C)": (150, 420), "Brazing Dwell (≥583°C)": (150, 99999)},
    "NB1 (CDS/KN9/12SHP)": {"Dryer Max (°C)": (200, 350), "Debinder Max (°C)": (300, 375), "Brazing Max (°C)": (585, 607), "Dryer Dwell (≥200°C)": (90, 99999), "Debinder Dwell (≥300°C)": (150, 99999), "Brazing Dwell (≥577°C)": (120, 465)},
    "NB3 (KE8 : M2/EVO)": {"Dryer Max (°C)": (200, 375), "Brazing Max (°C)": (595, 606), "Dryer Dwell (≥200°C)": (90, 99999), "Brazing Dwell (≥550°C)": (420, 630), "Brazing Dwell (≥577°C)": (270, 420), "Brazing Dwell (≥591°C)": (90, 240)},
    "NB2 (Tahc)": {"Dryer Max (°C)": (200, 375), "Brazing Max (°C)": (596, 604), "Dryer Dwell (≥250°C)": (60, 99999), "Brazing Dwell (≥577°C)": (240, 420), "Brazing Dwell (≥591°C)": (90, 270)},
    "NB2 (Utahc)": {"Dryer Max (°C)": (200, 375), "Brazing Max (°C)": (596, 606), "Dryer Dwell (≥250°C)": (60, 99999), "Brazing Dwell (≥577°C)": (240, 420), "Brazing Dwell (≥591°C)": (90, 270)},
    "NB3 (BTM)": {"Dryer Max (°C)": (300, 375), "Brazing Max (°C)": (595, 608), "Dryer Dwell (≥300°C)": (120, 99999), "Brazing Dwell (≥577°C)": (240, 840), "Brazing Dwell (≥591°C)": (120, 720), "Brazing Dwell (≥600°C)": (0, 480)}
}

FURNACE_CONFIGS = {
    "NB1": {
        "line_speed_mpm": 1.400, "trigger_temp_brazing": 577.0,
        "zones": [{"num": 1, "name": "Dryer Z#1", "start": 0.00, "length": 3.15, "group": "Dryer"}, {"num": 2, "name": "Dryer Z#2", "start": 3.15, "length": 3.13, "group": "Dryer"}, {"num": 3, "name": "EXT Dryer", "start": 6.27, "length": 0.70, "group": "Dryer"}, {"num": 4, "name": "ENT DB", "start": 6.97, "length": 0.67, "group": "Debinder"}, {"num": 5, "name": "DB Z#1", "start": 7.64, "length": 3.13, "group": "Debinder"}, {"num": 6, "name": "DB Z#2", "start": 10.77, "length": 2.60, "group": "Debinder"}, {"num": 7, "name": "DB Z#3", "start": 13.37, "length": 2.60, "group": "Debinder"}, {"num": 8, "name": "DB Z#4", "start": 15.97, "length": 3.13, "group": "Debinder"}, {"num": 9, "name": "XFER#1", "start": 19.10, "length": 2.71, "group": "Heating"}, {"num": 10, "name": "Z#1", "start": 21.81, "length": 3.14, "group": "Heating"}, {"num": 11, "name": "Z#2", "start": 24.95, "length": 2.68, "group": "Heating"}, {"num": 12, "name": "Z#3", "start": 27.63, "length": 2.72, "group": "Heating"}, {"num": 13, "name": "Z#4", "start": 30.35, "length": 2.04, "group": "Heating"}, {"num": 14, "name": "Z#5", "start": 32.39, "length": 2.00, "group": "Heating"}, {"num": 15, "name": "Z#6", "start": 34.39, "length": 2.00, "group": "Heating"}, {"num": 16, "name": "Z#7", "start": 36.39, "length": 2.29, "group": "Heating"}, {"num": 17, "name": "WatCool#1", "start": 38.68, "length": 2.39, "group": "Cooling"}, {"num": 18, "name": "WatCool#2", "start": 41.07, "length": 1.90, "group": "Cooling"}, {"num": 19, "name": "Exit curtain box", "start": 42.97, "length": 1.90, "group": "Cooling"}, {"num": 20, "name": "XFER#2", "start": 44.87, "length": 0.60, "group": "Cooling"}, {"num": 21, "name": "Air Cool#1", "start": 45.47, "length": 1.25, "group": "Cooling"}, {"num": 22, "name": "Air Cool#2", "start": 46.72, "length": 1.25, "group": "Cooling"}, {"num": 23, "name": "Exit", "start": 47.97, "length": 1.85, "group": "Cooling"}],
        "stages": [{"Stage": "Dryer", "Start (m)": 0.00, "End (m)": 6.28, "thresh": 200.0}, {"Stage": "Debinder", "Start (m)": 7.64, "End (m)": 19.10, "thresh": 300.0}, {"Stage": "Brazing", "Start (m)": 21.81, "End (m)": 42.97, "thresh": 577.0}]
    },
    "NB2": {
        "line_speed_mpm": 1.560, "trigger_temp_brazing": 577.0,
        "zones": [{"num": 1, "name": "DryOff-Z#1", "start": 0.00, "length": 2.80, "group": "Dryer"}, {"num": 2, "name": "DryOff-Z#2", "start": 2.80, "length": 2.80, "group": "Dryer"}, {"num": 3, "name": "Xfer1", "start": 5.60, "length": 3.13, "group": "Dryer"}, {"num": 4, "name": "Z#1", "start": 8.73, "length": 3.60, "group": "Heating"}, {"num": 5, "name": "Z#2", "start": 12.33, "length": 2.70, "group": "Heating"}, {"num": 6, "name": "Z#3", "start": 15.03, "length": 2.40, "group": "Heating"}, {"num": 7, "name": "Z#4", "start": 17.43, "length": 2.10, "group": "Heating"}, {"num": 8, "name": "Z#5", "start": 19.53, "length": 2.30, "group": "Heating"}, {"num": 9, "name": "Z#6", "start": 21.83, "length": 1.90, "group": "Heating"}, {"num": 10, "name": "Z#7", "start": 23.73, "length": 2.20, "group": "Heating"}, {"num": 11, "name": "Xfer2", "start": 25.93, "length": 0.80, "group": "Heating"}, {"num": 12, "name": "Watcol1", "start": 26.73, "length": 1.75, "group": "Cooling"}, {"num": 13, "name": "Watcol2", "start": 28.48, "length": 1.85, "group": "Cooling"}, {"num": 14, "name": "Exit curtain box", "start": 30.33, "length": 2.30, "group": "Cooling"}, {"num": 15, "name": "Airc1", "start": 32.63, "length": 1.25, "group": "Cooling"}, {"num": 16, "name": "Airc2", "start": 33.88, "length": 1.25, "group": "Cooling"}, {"num": 17, "name": "Exit", "start": 35.13, "length": 1.80, "group": "Cooling"}],
        "stages": [{"Stage": "Dryer", "Start (m)": 0.00, "End (m)": 5.60, "thresh": 200.0}, {"Stage": "Brazing", "Start (m)": 8.73, "End (m)": 30.33, "thresh": 577.0}]
    },
    "NB3": {
        "line_speed_mpm": 1.270, "trigger_temp_brazing": 577.0,
        "zones": [{"num": 1, "name": "XFER", "start": 0.00, "length": 0.10, "group": "Dryer"}, {"num": 2, "name": "Dryer#1", "start": 0.10, "length": 1.85, "group": "Dryer"}, {"num": 3, "name": "Dryer#2", "start": 1.95, "length": 1.85, "group": "Dryer"}, {"num": 4, "name": "Dryer#3", "start": 3.80, "length": 1.95, "group": "Dryer"}, {"num": 5, "name": "XFER#1", "start": 5.75, "length": 3.39, "group": "Dryer"}, {"num": 6, "name": "Z#1", "start": 9.14, "length": 3.60, "group": "Heating"}, {"num": 7, "name": "Z#2", "start": 12.74, "length": 2.75, "group": "Heating"}, {"num": 8, "name": "Z#3", "start": 15.49, "length": 2.30, "group": "Heating"}, {"num": 9, "name": "Z#4", "start": 17.79, "length": 2.10, "group": "Heating"}, {"num": 10, "name": "Z#5", "start": 19.89, "length": 2.10, "group": "Heating"}, {"num": 11, "name": "Z#6", "start": 21.99, "length": 1.90, "group": "Heating"}, {"num": 12, "name": "Z#7", "start": 23.89, "length": 1.63, "group": "Heating"}, {"num": 13, "name": "WatCoo#1", "start": 25.52, "length": 2.56, "group": "Cooling"}, {"num": 14, "name": "WatCoo#2", "start": 28.08, "length": 1.90, "group": "Cooling"}, {"num": 15, "name": "Exit curtain box", "start": 29.98, "length": 1.90, "group": "Cooling"}, {"num": 16, "name": "XFER#2", "start": 31.88, "length": 0.60, "group": "Cooling"}, {"num": 17, "name": "AirCoo#1", "start": 32.48, "length": 1.25, "group": "Cooling"}, {"num": 18, "name": "AirCoo#2", "start": 33.73, "length": 1.25, "group": "Cooling"}, {"num": 19, "name": "Exit", "start": 34.98, "length": 1.85, "group": "Cooling"}],
        "stages": [{"Stage": "Dryer", "Start (m)": 0.00, "End (m)": 5.75, "thresh": 200.0}, {"Stage": "Brazing", "Start (m)": 9.14, "End (m)": 29.98, "thresh": 577.0}]
    }
}

RECORDER_STANDARDS = {
    "NB1": {
        "Top": [(577, 587), (609, 619), (613, 623), (616, 626), (613, 623), (609, 619), (609, 615)],
        "Bottom": [(601, 611), (611, 621), (615, 625), (618, 628), (615, 625), (611, 621), (609, 615)],
        "Dryer": [(225, 255), (245, 275)],
        "Debinder": [(265, 295), (290, 320), (320, 350), (335, 365)]
    },
    "NB2": {
        "Top": [(585, 595), (609, 619), (613, 623), (614, 624), (612, 622), (606, 616), (606, 612)],
        "Bottom": [(585, 595), (609, 619), (613, 623), (614, 624), (612, 622), (606, 616), (606, 612)],
        "Dryer": [(295, 325), (325, 355)],
        "Debinder": []
    },
    "NB3": {
        "Top": [(598, 608), (609, 619), (618, 628), (624, 634), (618, 628), (616, 626), (611, 617)], 
        "Bottom": [(603, 613), (614, 624), (621, 631), (624, 634), (623, 633), (621, 631), (616, 622)],
        "Dryer": [(300, 330), (315, 345), (320, 350)],
        "Debinder": []
    }
}

CH_NB1 = [
    ('CH001', 'Top Z#1', '°C'), ('CH002', 'Top Z#2', '°C'), ('CH003', 'Top Z#3', '°C'), ('CH004', 'Top Z#4', '°C'),
    ('CH005', 'Top Z#5', '°C'), ('CH006', 'Top Z#6', '°C'), ('CH007', 'Top Z#7', '°C'), ('CH008', 'Bottom Z#1', '°C'),
    ('CH009', 'Bottom Z#2', '°C'), ('CH010', 'Bottom Z#3', '°C'), ('CH011', 'Bottom Z#4', '°C'), ('CH012', 'Bottom Z#5', '°C'),
    ('CH013', 'Bottom Z#6', '°C'), ('CH014', 'Bottom Z#7', '°C'), ('CH015', 'EXIT O2', 'ppm'), ('CH019', 'ENTRANCE O2', 'ppm'),
    ('CH016', 'Dryer #1', '°C'), ('CH017', 'Dryer #2', '°C'), ('CH018', 'N2 .1', 'm3/hr'), ('CH020', 'DEW POINT', 'Cdp'),
]

CH_NB2 = [
    ('CH001', 'Top Z#1', '°C'), ('CH002', 'Top Z#2', '°C'), ('CH003', 'Top Z#3', '°C'), ('CH004', 'Top Z#4', '°C'),
    ('CH005', 'Top Z#5', '°C'), ('CH006', 'Top Z#6', '°C'), ('CH007', 'Top Z#7', '°C'), ('CH008', 'Bottom Z#1', '°C'),
    ('CH009', 'Bottom Z#2', '°C'), ('CH010', 'Bottom Z#3', '°C'), ('CH011', 'Bottom Z#4', '°C'), ('CH012', 'Bottom Z#5', '°C'),
    ('CH013', 'Bottom Z#6', '°C'), ('CH014', 'Bottom Z#7', '°C'), ('CH015', 'O2 EXIT', 'ppm'), ('CH018', 'O2 ENTRANCE', 'ppm'),
    ('CH016', 'Dryer #1', '°C'), ('CH017', 'Dryer #2', '°C'),
]

COLORS_TOP = ['#FF0000', '#008000', '#0000FF', '#8A2BE2', '#A52A2A', '#FFA500', '#9ACD32']
COLORS_BOT = ['#ADD8E6', '#FF69B4', '#808080', '#FF0000', '#008000', '#0000FF', '#8A2BE2']
COLORS_DRY = {'CH016':'#FFA500', 'CH017':'#9ACD32'}
COLORS_O2_NB1 = {'CH015':'#A52A2A', 'CH019':'#ADD8E6'}
COLORS_O2_NB2 = {'CH015':'#A52A2A', 'CH018':'#ADD8E6'}
COLORS_N2 = {'CH018': '#2E75B6'}
COLORS_DEW = {'CH020': '#1D9E75'}

# ==============================================================================
# SIMULATION ZONES & MODELS MAPPING
# ==============================================================================
FURNACE_ZONE_DATA = {
    "NB1": [
        {"name": "Entrance", "len": 2.00, "type": "Entrance"}, {"name": "Fluxer", "len": 2.70, "type": "Flux"},
        {"name": "Xfer", "len": 2.18, "type": "Xfer"}, {"name": "Dryer Z#1", "len": 6.03, "type": "Dryer"},
        {"name": "Dryer Z#2", "len": 6.03, "type": "Dryer"}, {"name": "EXT Dryer", "len": 0.68, "type": "Dryer"},
        {"name": "ENT DB", "len": 0.68, "type": "Debinder"}, {"name": "DB Z#1", "len": 3.10, "type": "Debinder"},
        {"name": "DB Z#2", "len": 2.60, "type": "Debinder"}, {"name": "DB Z#3", "len": 2.60, "type": "Debinder"},
        {"name": "DB Z#4", "len": 3.10, "type": "Debinder"}, {"name": "XFER#1", "len": 3.00, "type": "Xfer"},
        {"name": "Z#1", "len": 3.65, "type": "Heating"}, {"name": "Z#2", "len": 2.68, "type": "Heating"},
        {"name": "Z#3", "len": 2.36, "type": "Heating"}, {"name": "Z#4", "len": 2.02, "type": "Heating"},
        {"name": "Z#5", "len": 2.01, "type": "Heating"}, {"name": "Z#6", "len": 1.84, "type": "Heating"},
        {"name": "Z#7", "len": 2.81, "type": "Heating"}, {"name": "WatCool#1", "len": 2.39, "type": "Cooling"},
        {"name": "WatCool#2", "len": 1.41, "type": "Cooling"}, {"name": "Exit curtain", "len": 2.29, "type": "Cooling"},
        {"name": "XFER#2", "len": 0.22, "type": "Cooling"}, {"name": "Air Cool#1", "len": 1.25, "type": "Cooling"},
        {"name": "Air Cool#2", "len": 1.25, "type": "Cooling"}, {"name": "Exit", "len": 1.85, "type": "Exit"}
    ],
    "NB2": [
        {"name": "Entrance", "len": 2.00, "type": "Entrance"}, {"name": "Flux spray", "len": 4.70, "type": "Flux"},
        {"name": "Xfer 2", "len": 2.50, "type": "Xfer"}, {"name": "DryOFF-Z#1", "len": 2.83, "type": "Dryer"},
        {"name": "DryOFF-Z#2", "len": 2.83, "type": "Dryer"}, {"name": "Xfer1", "len": 3.00, "type": "Xfer"},
        {"name": "Z#1", "len": 3.65, "type": "Heating"}, {"name": "Z#2", "len": 2.68, "type": "Heating"},
        {"name": "Z#3", "len": 2.36, "type": "Heating"}, {"name": "Z#4", "len": 2.02, "type": "Heating"},
        {"name": "Z#5", "len": 2.01, "type": "Heating"}, {"name": "Z#6", "len": 1.84, "type": "Heating"},
        {"name": "Z#7", "len": 2.81, "type": "Heating"}, {"name": "WatCool#1", "len": 2.39, "type": "Cooling"},
        {"name": "WatCool#2", "len": 1.41, "type": "Cooling"}, {"name": "Exit curtain", "len": 2.30, "type": "Cooling"},
        {"name": "Airc1", "len": 1.25, "type": "Cooling"}, {"name": "Airc2", "len": 1.25, "type": "Cooling"},
        {"name": "Exit", "len": 1.80, "type": "Exit"}
    ],
    "NB3": [
        {"name": "Entrance", "len": 0.90, "type": "Entrance"}, {"name": "Fluxer", "len": 4.05, "type": "Flux"},
        {"name": "XFER", "len": 2.52, "type": "Xfer"}, {"name": "Dryer#1", "len": 1.88, "type": "Dryer"},
        {"name": "Dryer#2", "len": 1.88, "type": "Dryer"}, {"name": "Dryer#3", "len": 1.88, "type": "Dryer"},
        {"name": "XFER#1", "len": 3.00, "type": "Xfer"}, {"name": "Z#1", "len": 3.65, "type": "Heating"},
        {"name": "Z#2", "len": 2.68, "type": "Heating"}, {"name": "Z#3", "len": 2.36, "type": "Heating"},
        {"name": "Z#4", "len": 2.02, "type": "Heating"}, {"name": "Z#5", "len": 2.01, "type": "Heating"},
        {"name": "Z#6", "len": 1.84, "type": "Heating"}, {"name": "Z#7", "len": 2.81, "type": "Heating"},
        {"name": "WatCool#1", "len": 2.39, "type": "Cooling"}, {"name": "WatCool#2", "len": 1.41, "type": "Cooling"},
        {"name": "Exit curtain", "len": 2.50, "type": "Cooling"}, {"name": "AirCool#1", "len": 1.25, "type": "Cooling"},
        {"name": "AirCool#2", "len": 1.25, "type": "Cooling"}, {"name": "Exit", "len": 1.85, "type": "Exit"}
    ]
}

ZONE_COLORS = {
    "Entrance": "#D3D3D3", "Dryer": "#FFD700", "Debinder": "#FFA500", "Heating": "#FF4500",
    "Cooling": "#87CEFA", "Flux": "#9370DB", "Xfer": "#D3D3D3", "Exit": "#A9A9A9"
}

IMAGE_MAPPING = { "NB1": "Pic NB1.png", "NB2": "Pic NB2.png", "NB3": "Pic NB3.png" }

# ==============================================================================
# FUNCTIONS: SIMULATION
# ==============================================================================
def identify_furnace_type(text_to_search):
    furnace_id = "NB3" # Default
    if re.search(r'\b(RAD|CDS|KN9|12SHP|DNGA|P42QR|P42V|SU2|F44|Y4L)\b', text_to_search, re.IGNORECASE): 
        furnace_id = "NB1"
    elif re.search(r'\b(Utahc|UT|Tahc|G2|NB2)\b', text_to_search, re.IGNORECASE): 
        furnace_id = "NB2"
    elif re.search(r'\b(BTM|KE8|M2|EVO|NB3)\b', text_to_search, re.IGNORECASE): 
        furnace_id = "NB3"
    elif re.search(r'\bWK\d{1,2}\b', text_to_search, re.IGNORECASE) or re.search(r'\b\d{6}\b', text_to_search): 
        furnace_id = "NB1"
    else:
        f_match = re.search(r'NB\s*Furnace\s*0?([123])\b|NB\s*#?\s*0?([123])\b|NB-0?([123])\b', text_to_search, re.IGNORECASE)
        if f_match: 
            found_num = next(g for g in f_match.groups() if g is not None)
            furnace_id = f"NB{found_num}"
    return furnace_id

def detect_furnace_from_dataframe(df):
    text_data = ""
    for col in ['Description', 'Reference', 'WORKCENTERLIST']:
        if col in df.columns:
            text_data += " " + " ".join(df[col].dropna().astype(str).tolist())
    text_data = text_data.upper()
    nb1_score = sum(text_data.count(kw) for kw in ["16XHP", "27XHP", "12XHP", "CMFB", "D15B", "DNGA", "P42QR", "W42JK", "F44", "F48", "DEMIO", "5H45V", "KN9", "N117", "YR9", "SU2", "Y4L", "GC7", "RADIATOR", "CONDENSER", "APU450"])
    nb2_score = sum(text_data.count(kw) for kw in ["TAHC", "UTAHC", "CHORA", "HEATER CORE", "TK/NX5", "APU350"])
    nb3_score = sum(text_data.count(kw) for kw in ["KE8", "X11C", "T34", "RBC", "K2", "J4LL", "BTM", "EVO", "CORION", "EVAPORATOR", "MAIN_COOLER", "APU214"])
    
    if nb1_score == 0 and nb2_score == 0 and nb3_score == 0: return None
    scores = {"NB1": nb1_score, "NB2": nb2_score, "NB3": nb3_score}
    return max(scores, key=scores.get)

def get_model_info(description, furnace_id):
    desc = str(description).upper()
    if furnace_id == "NB1":
        if "16XHP" in desc and "123T" in desc: return 1.041, 2
        if "27XHP" in desc and any(kw in desc for kw in ["64T", "73T", "123T"]): return 0.887, 2
        if "12XHP" in desc and "SU2" in desc: return 0.660, 2
        if "CMFB" in desc: return 0.640, 2
        if "D15B" in desc: return 0.610, 2
        if "DNGA" in desc and not any(kw in desc for kw in ["DNGA1", "DNGA2"]): return 0.610, 2
        if "SU2" in desc: return 0.660, 2
        if "42QR" in desc or "P42QR" in desc or "W42JK" in desc: return 0.760, 2
        if "F44" in desc or "F48" in desc: return 0.660, 2
        if "5H45V" in desc: return 0.670, 2
        if "KN6 #6" in desc or "KN9 #6" in desc: return 0.760, 1
        return 0.790, 2 
    elif furnace_id == "NB2":
        if "P13C" in desc: return 0.370, 4
        if "SFTP" in desc or "KAMAZ" in desc: return 0.380, 3
        return 0.380, 4
    elif furnace_id == "NB3":
        if "N173" in desc or "KEI EV" in desc: return 1.400, 4
        if "N175" in desc or "OUTLANDER" in desc: return 1.260, 4
        if "M48" in desc: return 1.435, 2
        if "KE8" in desc: return 0.370, 3
        if any(kw in desc for kw in ["NX5", "J4LL", "J2LL", "D2LL"]): return 0.363, 2
        if "RBC" in desc or "D12A" in desc: return 0.363, 3
        if "U825" in desc or "EMK" in desc: return 0.513, 3
        return 0.463, 3
    return 0.660, 2

# ==============================================================================
# DATAPAQ .PAQ UTILITY FUNCTIONS
# ==============================================================================
def extract_paq_collection_started(file_bytes):
    epoch = datetime(1899, 12, 30)
    try:
        decompressed_buffers = []
        parts = file_bytes.split(b'ZLIB')
        for part in parts[1:]:
            for offset in range(16):
                try: decompressed_buffers.append(zlib.decompress(part[offset:]))
                except: pass
        parts2 = file_bytes.split(b'\x78\x9c')
        for part in parts2[1:]:
            try: decompressed_buffers.append(zlib.decompress(b'\x78\x9c' + part))
            except: pass

        for buf in decompressed_buffers:
            idx = buf.find(b'CTriggerQuantity')
            if idx != -1:
                sub_buf = buf[idx:idx+100]
                for i in range(len(sub_buf) - 8):
                    try:
                        val = struct.unpack('<d', sub_buf[i:i+8])[0]
                        if 36526.0 <= val <= 51135.0:
                            dt = epoch + timedelta(days=val)
                            if dt.year > 2000: return dt
                    except: pass
        
        valid_times = []
        for buf in decompressed_buffers:
            for i in range(len(buf) - 8):
                try:
                    val = struct.unpack('<d', buf[i:i+8])[0]
                    if 36526.0 <= val <= 51135.0:
                        dt = epoch + timedelta(days=val)
                        if dt.year > 2000 and (dt.hour != 0 or dt.minute != 0 or dt.second != 0):
                            valid_times.append(dt)
                except: pass
                
        if valid_times:
            years = [d.year for d in valid_times]
            filtered_times = [d for d in valid_times if d.year == statistics.median(years)]
            if filtered_times: return min(filtered_times)
        return None
    except Exception: return None

def style_inspection_matrix(row, variant, check_dryer_max=False):
    styles = [''] * len(row)
    rules = VALIDATION_RULES.get(variant, {})
    probe_name = row.get("Probe", "")
    for i, col in enumerate(row.index):
        if col == "Probe": continue
        val = row[col]
        base_bg = ""
        if "Dryer" in col: base_bg = "background-color: rgba(255, 235, 156, 0.15);" 
        elif "Debinder" in col: base_bg = "background-color: rgba(255, 199, 119, 0.15);" 
        elif "Brazing" in col: base_bg = "background-color: rgba(255, 160, 160, 0.15);" 
            
        if val == "***":
            styles[i] = f'{base_bg} color: #f39c12; font-weight: bold; text-align: center;'
            continue

        rule = rules.get(col)
        if variant == "NB1 (CDS/KN9/12SHP)" and col == "Brazing Dwell (≥577°C)":
            rule = (240, 465) if probe_name in ["PB#1", "PB#5"] else (120, 465)
        if not check_dryer_max and ("Dryer Max" in col or "Dryer Dwell" in col): rule = None
            
        is_fail = False
        if pd.isna(val) or val == "00:00:00" or val == "" or val == 0 or val == "N/A":
            if rule and rule[0] > 0: is_fail = True
        else:
            if rule:
                min_v, max_v = rule
                if "Max (°C)" in col:
                    try:
                        if not (min_v <= float(val) <= max_v): is_fail = True
                    except: pass
                elif "Dwell" in col:
                    try:
                        parts = str(val).split(':')
                        if len(parts) == 3:
                            total_s = int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
                            if not (min_v <= total_s <= max_v): is_fail = True
                    except: pass
                    
        if rule:
            styles[i] = f'background-color: rgba(255, 0, 0, 0.25); color: #d32f2f; font-weight: bold; border: 1px solid #d32f2f;' if is_fail else f'{base_bg} color: #009900; font-weight: bold;'
        else: styles[i] = f'{base_bg}'
    return styles

def highlight_row_by_group(row):
    bg_color = GROUP_COLORS.get(row["Group"], "")
    return [f"background-color: {bg_color}"] * len(row) if bg_color else [""] * len(row)

def decompress_stream(ole_obj, stream_name):
    try:
        raw_data = ole_obj.openstream(stream_name).read()
        zlib_data = raw_data[8:] if raw_data.startswith(b'ZLIB') else raw_data
        try: return zlib.decompress(zlib_data)
        except: return zlib.decompress(zlib_data, -zlib.MAX_WBITS)
    except: return None

def extract_probe_series_autonomously(decomp_bytes):
    best_series = []
    for offset in range(0, min(12000, len(decomp_bytes) - 800), 1):
        rem = len(decomp_bytes) - offset
        cnt = rem // 8
        if cnt < 500: continue
        try: vals = struct.unpack(f"<{cnt}d", decomp_bytes[offset : offset + cnt * 8])
        except: continue
        clean_vals, glitch_count = [], 0
        for v in vals:
            if isinstance(v, float) and -50.0 <= v <= 1000.0:
                clean_vals.append(v)
                glitch_count = 0
            else:
                glitch_count += 1
                if len(clean_vals) > 500:
                    if glitch_count <= 30: clean_vals.append(clean_vals[-1] if clean_vals else 0.0)
                    else: break
                elif glitch_count > 3: clean_vals = []
        if len(clean_vals) > len(best_series) and max(clean_vals) > 100.0: best_series = clean_vals
    return best_series

def format_dwell_time(total_seconds):
    if pd.isna(total_seconds) or total_seconds == 0: return "00:00:00"
    m, s = divmod(total_seconds, 60)
    h, m = divmod(m, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"

def clean_paq_text(raw_text):
    if not raw_text: return ""
    text = re.split(r'\\\\', raw_text)[0]
    parts = re.split(r'\b(?:CProbe|CSampleInterval|CAxisCustomUnits|CPaqfile|CByteDataArray|CProbeResult|CFurnaceRecipe|CZoom|CProbeMapEntry\w*|cho1-sv|CProcessFile|COven|CZone|CRecipe|CProduct|CAnalysisParameters|CAlarmParameters|CAlarmProbes|CAlarmParametersTime|CRiseFallRange|CTemperatureLimits|CTimeLimits|CCustomUnits|CLineSpeed|COvenStart|CProcessOptimisation|CToleranceCurve|CVersionInfo|CLogger|CSystemInfo|CMaximumMinimumAnalysisParameters|CTimeAtMeasurementAnalysisParameters)\b', text)
    cleaned_parts = []
    for p in parts:
        p = re.sub(r'^[>#;\.,\|]+', '', p).strip() 
        if len(p) < 3: continue
        p = re.sub(r'\b(Untitled|Entry Zone|XFER|WatCool|Exit curtain|AirCool|Exit Zone|Dryer#1|VSTS Exit Dryer|Exit Dryer|0Hl|!@f|"onB|aaa\.\.\.|FFGCC|bbbRRR|LNNSQ|OD@)\b', ' ', p, flags=re.IGNORECASE)
        is_rec_str = re.search(r'(?i)(During\s*datapaq|O2|WJ|Braze\s*Temp|Top\s*\(|Bot\s*\(|Furnace\s*Parameter|N2\s*Flow|Flux\s*Spray|Frequency\s*motor|NB\s*Top|NB\s*Bot)', p)
        if not is_rec_str:
            if re.search(r'([^\-\/0-9])\1{4,}', p) or re.search(r'[@^\$|~<>{}\[\]]{2,}', p): continue 
        p = re.sub(r'#[0-9]{3,}', '', p)
        p = re.sub(r'\s+', ' ', p).strip()
        if p and len(p) >= 3: cleaned_parts.append(p)
    return " ".join(cleaned_parts)

def clean_probe_location(loc_desc):
    loc_desc = re.sub(r'^[^A-Za-z]*(Top|Bottom|Middle|Left|Right|Core)', r'\1', loc_desc, flags=re.IGNORECASE)
    return re.sub(r'\b[A-Z](Left|Right|Middle|Bottom|Top)\b', r'\1', loc_desc, flags=re.IGNORECASE)

def parse_operator_and_metadata(comments_list):
    combined = " ".join(comments_list)
    op, site, comp = "N/A", "N/A", "VSTS"
    
    m_site = re.search(r'(Power\s+Chonburi|Chonburi|Plant\s+\d+|Factory\s+\d+)', combined, re.IGNORECASE)
    if m_site: site = m_site.group(1).strip()
    
    clean_notes = re.sub(r'^\s*CAlarm\s*', '', combined, flags=re.IGNORECASE)
    m_op = re.search(r'^([A-Za-z/]+)\s+(?:Datapaq|NB[1-3]|Monthly|WK|date|product|validation|run|test|DBLog|disconnected|Power|Chonburi|Plant|Factory)', clean_notes, re.IGNORECASE)
    if m_op: op = m_op.group(1).strip()
    elif re.search(r'\b(Niwat|Sunisa|Mongkhon|Sompong|Jintana|Operator)\b', clean_notes, re.IGNORECASE):
        op = re.search(r'\b(Niwat|Sunisa|Mongkhon|Sompong|Jintana|Operator)\b', clean_notes, re.IGNORECASE).group(1).strip()

    log_marker = re.search(r'(disconnected:|DBLog Cleared:|DP2300|CommIn:LOGGER_|USB_NOTIFY_|TickRate|VBatt|\(USB_VALID\)|CommsIn\s+\d+|LoggerState_NewState:|trigger_search|DP\d{4}|Logger:|Battery:|Firmware:|Serial No:)', clean_notes, flags=re.IGNORECASE)
    if log_marker: clean_notes = clean_notes[:log_marker.start()].strip()
    
    for token in [op, comp, site, "CAlarm"]:
        if token != "N/A": clean_notes = re.sub(rf'^[\s\W]*{re.escape(token)}\b[\s\W]*', '', clean_notes, flags=re.IGNORECASE)

    clean_notes = re.sub(r'NB\s+with\s+Debinder\s+NB\s+Furnace\s+Total\s*;\s*[\d,]+\s*mm', '', clean_notes, flags=re.IGNORECASE)
    clean_notes = re.split(r':?\s*NB\s*[1-3]\s*with\s*Debinder', clean_notes, flags=re.IGNORECASE)[0]
    
    chop_pattern = r'\b(NB\s*\d\s*DryOff|DryOff-Z|Xfer2\s*Watcol|Watcol1|AN\s*h8|ljjSQP|xwTLL)\b'
    split_notes = re.split(chop_pattern, clean_notes, flags=re.IGNORECASE)
    if len(split_notes) > 1: clean_notes = split_notes[0].strip()
        
    garbage_start = re.search(r'([A-Za-z]\\[A-Za-z]|[\$\#\^\~]{2,}|\?[A-Z]{2,}|[a-z]{2,}\~|\bKO\\|\b\d{1,2}:\d{1,2}[A-Z]+)', clean_notes)
    if garbage_start: clean_notes = clean_notes[:garbage_start.start()]
        
    garbage_regex = r'(C:\\Program Files|IJ@1|a@FGr|YW@\.|dhmquz|QUZ|rx\s+knv|V\^e|ipyw~|MSYmqw~|AFMEKO|FIL257|CVersionInfo|1w-!|zfo@|8gDi|R@\?m|MQTDFI|HKN\*,|Double m\b|double m\b)'
    clean_notes = re.split(garbage_regex, clean_notes, flags=re.IGNORECASE)[0]
    
    clean_notes = re.sub(r'(?i)\b[a-z]:\\[^\s]*', '', clean_notes)
    clean_notes = re.sub(r'(?i)https?://[^\s]*', '', clean_notes)
    clean_notes = re.sub(r'(?i)\\\\[a-z0-9_]+\\[^\s]*', '', clean_notes)
    clean_notes = re.sub(r'[^\w\s\.\,\-\/\(\)\=\+:\%\*]', ' ', clean_notes)
    clean_notes = re.sub(r'\b[A-Z0-9]{15,}\b', '', clean_notes) 
    
    extra_probes = []
    probe_matches = re.finditer(r'(?:Probe\s*no\.?\s*(?:[1-9]|10)|PB#(?:[1-9]|10)|#(?:[1-9]|10)\s*\().*?(?=\Z|\bProbe\s*no|\bPB#|#(?:[1-9]|10)\s*\()', clean_notes, flags=re.IGNORECASE)
    for m in probe_matches:
        p_text = m.group(0).strip()
        if re.search(r'(core|bottom|top|left|right|manifold|pipe|drill)', p_text, re.IGNORECASE):
            extra_probes.append(p_text)
            
    loc_cutoff = re.search(r'\b(Bottom\s*-\s*(Top|Bottom|Center|Left|Right)|Top\s*-\s*(Top|Bottom|Center|Left|Right)|Middle\s*left|Middle\s*right|Right\s*core|Left\s*core|NB\s*\d\s*with\s*Debinder|Dryer\s*Z\s*1)\b', clean_notes, re.IGNORECASE)
    if loc_cutoff: clean_notes = clean_notes[:loc_cutoff.start()]
        
    clean_notes = re.sub(r'\b(hzgxdvN|ljjSQP|xwTLL|nif\s*jgni)\b', '', clean_notes, flags=re.IGNORECASE)
    clean_notes = re.sub(r'\s:\s(?=[A-Za-z])', ' ', clean_notes)
    clean_notes = re.sub(r'\s{2,}', ' ', clean_notes)
    clean_notes = re.sub(r'^[.,;\s:]+', '', clean_notes)
    clean_notes = re.sub(r'[\.,\s]+$', '.', clean_notes).strip()
    
    return op, comp, site, clean_notes if clean_notes else "N/A", extra_probes

@st.cache_data
def process_paq_file(file_bytes, filename):
    ole_bytes = io.BytesIO(file_bytes)
    ole = olefile.OleFileIO(ole_bytes)
    
    real_start_dt = extract_paq_collection_started(file_bytes)
    extracted_date, extracted_time_str, date_found = pd.Timestamp.now().date(), "00:00:00", False

    if real_start_dt:
        extracted_date = real_start_dt.date()
        extracted_time_str = real_start_dt.strftime("%I:%M:%S %p")
        date_found = True
        process_start_dt_str = real_start_dt.strftime('%Y-%m-%d <br> %H:%M:%S')
    else:
        m_ymd = re.search(r'(20[1-3]\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])', filename)
        m_y_m_d = re.search(r'(20[1-3]\d)[-_](0[1-9]|1[0-2])[-_](0[1-9]|[12]\d|3[01])', filename)
        m_d_m_y = re.search(r'(0[1-9]|[12]\d|3[01])[-_](0[1-9]|1[0-2])[-_](20[1-3]\d)', filename)
        try:
            if m_ymd: extracted_date, date_found = pd.to_datetime(f"{m_ymd.group(1)}-{m_ymd.group(2)}-{m_ymd.group(3)}").date(), True
            elif m_y_m_d: extracted_date, date_found = pd.to_datetime(f"{m_y_m_d.group(1)}-{m_y_m_d.group(2)}-{m_y_m_d.group(3)}").date(), True
            elif m_d_m_y: extracted_date, date_found = pd.to_datetime(f"{m_d_m_y.group(3)}-{m_d_m_y.group(2)}-{m_d_m_y.group(1)}").date(), True
        except: pass
        
        try:
            mtime = ole.root.getmtime()
            if mtime:
                if not date_found: extracted_date = mtime.date()
                extracted_time_str = mtime.strftime("%I:%M:%S %p")
            else:
                for st_path in ole.listdir():
                    smtime = ole.getmtime(st_path)
                    if smtime:
                        if not date_found: extracted_date = smtime.date()
                        extracted_time_str = smtime.strftime("%I:%M:%S %p")
                        break
        except: pass
        process_start_dt_str = "Error calculating absolute time"

    raw_texts = []
    embedded_img = None
    for stream_path in ole.listdir():
        try:
            raw_b = ole.openstream(stream_path).read()
            if not raw_b: continue
            data_b = raw_b
            if raw_b.startswith(b'ZLIB') or b'x\x9c' in raw_b[:20]:
                try: data_b = zlib.decompress(raw_b[8:] if raw_b.startswith(b'ZLIB') else raw_b)
                except:
                    try: data_b = zlib.decompress(raw_b[8:] if raw_b.startswith(b'ZLIB') else raw_b, -zlib.MAX_WBITS)
                    except: pass
            if embedded_img is None and len(data_b) > 500:
                for header in [b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff', b'BM']:
                    idx = data_b.find(header)
                    if idx != -1:
                        try: 
                            embedded_img = Image.open(io.BytesIO(data_b[idx:]))
                            break
                        except: pass
            ascii_matches = re.findall(rb'[\x20-\x7E]{4,}', data_b)
            for m in ascii_matches: raw_texts.append(m.decode('ascii', errors='ignore').strip())
        except: continue

    if not real_start_dt:
        for s in raw_texts:
            if not date_found:
                m_date = re.search(r'\b(20\d{2}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]20\d{2})\b', s)
                if m_date:
                    try: 
                        extracted_date = pd.to_datetime(m_date.group(1), errors='coerce').date()
                        if pd.notna(extracted_date): date_found = True
                    except: pass
            m_time_ampm = re.search(r'\b(0?[1-9]|1[0-2]):([0-5]\d)(?::([0-5]\d))?\s*([AaPp][Mm])\b', s)
            if m_time_ampm:
                hr, mn, sc, ampm = int(m_time_ampm.group(1)), int(m_time_ampm.group(2)), int(m_time_ampm.group(3)) if m_time_ampm.group(3) else 0, m_time_ampm.group(4).upper()
                extracted_time_str = f"{hr}:{mn:02d}:{sc:02d} {ampm}"
                break
            m_time_24h = re.search(r'\b([0-1]?\d|2[0-3]):([0-5]\d):([0-5]\d)\b', s)
            if m_time_24h:
                hr, mn, sc = int(m_time_24h.group(1)), int(m_time_24h.group(2)), int(m_time_24h.group(3))
                ampm = "AM" if hr < 12 else "PM"
                hr_12 = hr % 12
                if hr_12 == 0: hr_12 = 12
                extracted_time_str = f"{hr_12}:{mn:02d}:{sc:02d} {ampm}"
                break

    channel_mapping = {}
    num_logger_channels = 0
    for s in raw_texts:
        matches = re.findall(r'#probe\s+number\s+#(\d+)\s*=\s*(\d+)', s, re.IGNORECASE)
        for m in matches: channel_mapping[int(m[0])] = int(m[1])
        if num_logger_channels == 0:
            m_ch = re.search(r'#number of channels\s*=\s*(\d+)', s, re.IGNORECASE)
            if m_ch: num_logger_channels = int(m_ch.group(1))
    if num_logger_channels == 0: num_logger_channels = max(channel_mapping.values()) if channel_mapping else 10
    num_logger_channels = min(num_logger_channels, 10) 

    probe_streams = [s for s in ole.listdir() if len(s) >= 4 and s[0] == 'Paqfiles' and s[2] == 'ProbeResults']
    probe_streams = sorted(probe_streams, key=lambda x: x[-1])
    all_probes = {}
    for idx, stream_path in enumerate(probe_streams):
        stream_name = "/".join(stream_path)
        internal_idx = idx + 1
        physical_ch = channel_mapping.get(internal_idx, internal_idx)
        col_name = f"PB#{physical_ch}"
        d = decompress_stream(ole, stream_name)
        if d:
            series = extract_probe_series_autonomously(d)
            if series: all_probes[col_name] = series

    max_samples = max(len(v) for v in all_probes.values()) if all_probes else 0
    if max_samples == 0: return None

    aligned_probes = {k: (v + [np.nan] * (max_samples - len(v)) if len(v) < max_samples else v) for k, v in all_probes.items()}
    df_master = pd.DataFrame(aligned_probes)
    df_master.insert(0, "Time_Seconds", range(len(df_master)))
    base_date_ref = pd.Timestamp("1970-01-01 00:00:00")
    df_master.insert(1, "Time_Stamp", base_date_ref + pd.to_timedelta(df_master["Time_Seconds"], unit="s"))
    df_master.insert(2, "Time_HHMMSS", df_master["Time_Stamp"].dt.strftime('%H:%M:%S'))

    expected_cols = [f"PB#{i}" for i in range(1, 11)]
    for col in expected_cols:
        if col not in df_master.columns: df_master[col] = np.nan
    probe_cols = expected_cols
    invalid_cols = []
    
    for col in probe_cols:
        series = df_master[col].dropna()
        if len(series) == 0 or len(series) < len(df_master) * 0.20 or series.max() < 100.0:
            invalid_cols.append(col); df_master[col] = np.nan
            
    if not [c for c in probe_cols if c not in invalid_cols]: return None 
    
    SUSTAINED_SECONDS = 15
    probe_start_secs = {}
    for col in probe_cols:
        is_p60 = (df_master[col] >= 60.0)
        valid_p_mask = is_p60.copy()
        for i in range(1, SUSTAINED_SECONDS): valid_p_mask = valid_p_mask & is_p60.shift(-i, fill_value=False)
        probe_start_secs[col] = int(df_master[valid_p_mask].iloc[0]["Time_Seconds"]) if valid_p_mask.any() else 0

    valid_starts = [sec for sec in probe_start_secs.values() if sec > 0]
    detected_start_sec = min(valid_starts) if valid_starts else 0
    if valid_starts: first_probe_name = [k for k, v in probe_start_secs.items() if v == detected_start_sec][0]
    else:
        valid_p = [c for c in probe_cols if c not in invalid_cols]
        first_probe_name = valid_p[0] if valid_p else probe_cols[0]

    detected_start_hhmmss = df_master[df_master["Time_Seconds"] == detected_start_sec].iloc[0]["Time_HHMMSS"]

    found_comments, found_recipes, found_probes = [], [], []
    for s in raw_texts:
        if re.search(r'\\\\|\b[A-Z]:\\', s) or re.search(r'\.(ovn|prd|pro|rec|paq|jpg|png|bmp)\b', s, re.IGNORECASE) or re.search(r'\\Users\\|Desktop', s, re.IGNORECASE): continue
        s_clean = clean_paq_text(s)
        if not s_clean: continue
        is_probe = re.search(r'\b(cooler|drill&insert|inside H/D|manifold|core|PB#\d|Probe\s*no|Left\s*core|Right\s*core|Middle\s*core)\b', s_clean, re.IGNORECASE)
        is_note = re.search(r'\b(validation|product|new bar|WK\d|Loaded|Model|week\d|date\d|datapaq|spacer|gap|EVO|G100|Tahc)\b', s_clean, re.IGNORECASE)
        
        if is_probe and not is_note and len(s_clean) < 80:
            if s_clean not in found_probes: found_probes.append(s_clean)
        else:
            is_recipe = re.search(r"(?i)(During\s*datapaq|Furnace\s*Parameter|O2\s*Exit|ppm|CV\s*speed|Braze\s*Temp|Top\s*\(\'?C\'?\)|Bot\s*\(\'?C\'?\)|Top\s*:|Bot\s*:|Temp\s*Top|Temp\s*Bot|N2\s*Flow|WJ\s*Flow|Flux\s*Spray|NB\s*Top|NB\s*Bot|Frequency\s*motor)", s_clean)
            if is_recipe and re.search(r'(apply\s*flux|paste\s*flux|nocolok|loading\s*double|gap\s*\d+mm)', s_clean, re.IGNORECASE) and not re.search(r'(during\s*datapaq|WJ\s*Flow|Braze\s*Temp|Top\s*\()', s_clean, re.IGNORECASE):
                is_recipe = False
                
            if is_recipe:
                s_rec = s_clean
                note_part = ""
                match_during = re.search(r'(?i)(?:data\s*)?during\s*datapaq', s_rec)
                if match_during:
                    note_part = s_rec[:match_during.start()].strip()
                    s_rec = "Data during datapaq " + s_rec[match_during.end():]
                else:
                    match_recipe_start = re.search(r"(?i)(Furnace\s*Parameter|O2|N2\s*Flow|WJ|CV\s*speed|Braze\s*Temp|Top\s*\(\'?C\'?\)|Bot\s*\(\'?C\'?\)|Top\s*:|Bot\s*:|NB\s*Top|NB\s*Bot)", s_rec)
                    if match_recipe_start:
                        note_part = s_rec[:match_recipe_start.start()].strip()
                        s_rec = s_rec[match_recipe_start.start():]
                    else: note_part = s_rec 
                if note_part and note_part not in found_comments: found_comments.append(note_part)
                
                s_rec = re.sub(r'[\{\}\[\]\^\`\\]+', '', s_rec) 
                s_rec = re.sub(r'\b(?:CProcessFile|COven|CZone|CRecipe|CProduct|CAnalysisParameters|CToleranceCurve|CAlarmParametersDouble|CMaximumMinimumAnalysisParameters|CTimeAtMeasurementAnalysisParameters|CRiseFallAnalysisParameters|CSlopeAnalysisParameters|CPeakDifferenceAnalysisParameters|CAreaUnderCurveAnalysisParameters|CFurnaceSurveyAnalysisParameters)\b', '', s_rec).strip()
                s_rec = re.sub(r'cer<>Hz\}', '', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r'==\?mnojjo[^\s]+', '', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r'(N2\s*Flow=?)', r'\n\1', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r'(Flux\s*Spray)', r'\n\1', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r'(Frequency\s*motor)', r'\n\1', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r'(WJ Flow)', r'\n\1', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r'(NB Top Temp)', r'\n\1', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r'(NB Bot temp)', r'\n\1', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r'(NB\s*Top\s*Temp\s*:?)', r'\n\1', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r'(NB\s*Bot\s*temp\s*:?)', r'\n\1', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r'(Braze\s*Temp:?)', r'\n\1 ', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r'(BrazeTemp:?)', r'\n\1 ', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r'(Brazed temp:?)', r'\n\1 ', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r'(Brazing temp:?)', r'\n\1 ', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r"(Top\s*\(\'?C\'?\)\s*:?)", r'\n\1', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r"(Bot\s*\(\'?C\'?\)\s*:?)", r'\n\1', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r'(Temp\s*Top\s*:?)', r'\n\1', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r'(Temp\s*Bot\s*:?)', r'\n\1', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r'\b(Top\s*:)', r'\n\1', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r'\b(Bot\s*:)', r'\n\1', s_rec, flags=re.IGNORECASE)
                s_rec = re.sub(r' +', ' ', s_rec)
                s_rec = re.sub(r'\n\s+', '\n', s_rec)
                s_rec = re.sub(r'\n{2,}', '\n', s_rec).strip()
                if s_rec and s_rec not in found_recipes and s_rec != note_part: found_recipes.append(s_rec)
            else:
                if s_clean not in found_comments: found_comments.append(s_clean)

    operator_name, company, site, clean_comments_text, extra_probes = parse_operator_and_metadata(found_comments)
    
    valid_probes = [p for p in found_probes + extra_probes if not re.search(r'\b(DryOff|Xfer|Watcol|AirC|Exit curtain|AN h8|ljjSQP|xwTLL|ZY\+|nif jgni|Exit)\b', p, re.IGNORECASE)]

    probe_locations = {}
    unassigned_probes = []
    
    def clean_global_garbage(text):
        if not text or text == "N/A": return text
        text = re.sub(r'^[\s\W]*;>=ced\b\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^[\s\W]*;>=ced', '', text, flags=re.IGNORECASE) 
        text = re.sub(r'^[\s\W]*;>=[a-z]+\s*', '', text) 
        text = re.sub(r'^[\s\W]*(Niwat|Sunisa|Mongkhon|Sompong|Jintana|Operator)\b[\s\W]*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'[a-zA-Z_]{20,}~?', '', text) 
        text = re.sub(r'(?:[A-Z]{3,}==;|SRQBB)[^\n]*', '', text)
        text = re.sub(r'([3]{4,}[a-zA-Z\s]+)+[3]{4,}[^\n]*', '', text) 
        text = re.sub(r'[,H\s]*3{3,}[\sN,3a-zA-Z]*', '', text) 
        text = re.sub(r'\s*(\b\d{1,2}[a-zA-Z]?\s+\d{4,}\s+)?(3{6,}|2{6,}|1{6,}|0{6,}|\b\d{6,}\s+\d{6,})[^\n]*', '', text)
        garbage_match = re.search(r'([a-zA-Z])\1{4,}|([a-zA-Z]{2})\2{3,}|RSS\s+SS\s+SSS|SsSZ\)|Iapcd\s+iegg|PuSu\s+Yuuu|aucucu\s+luku|\bJsK\s+MQsQ|\bQYSsS\b|\bWiiolpqr\b|\bvuAuu\b|EQUdcgcfZadWaXY', text)
        if garbage_match: text = text[:garbage_match.start()]
        text = re.sub(r'[\s\.\,\-]+(?:24275|\d{4,6})\s*$', '', text) 
        text = re.sub(r'[\s,;:.\-\&\#\$\!\(\)\*\+]+$', '', text).strip()
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text if text else "N/A"

    temp_combined_probes = " ".join(valid_probes)
    clean_comments_text = clean_global_garbage(clean_comments_text)
    
    process_settings = clean_global_garbage("\n".join(found_recipes) if found_recipes else "Standard Recipe Parameters")
    process_settings = re.sub(r'\n{3,}', '\n\n', process_settings).strip()

    recipe_corpus = f"{process_settings} {clean_comments_text} {filename} {temp_combined_probes}"

    furnace_id, furnace_variant = "NB3", "NB3"
    if re.search(r'\bRAD\b', recipe_corpus, re.IGNORECASE): furnace_id, furnace_variant = "NB1", "NB1 (RAD)"
    elif re.search(r'\b(Utahc|UT)\b', recipe_corpus, re.IGNORECASE): furnace_id, furnace_variant = "NB2", "NB2 (Utahc)"
    elif re.search(r'\b(Tahc|G2|NB2)\b', recipe_corpus, re.IGNORECASE): furnace_id, furnace_variant = "NB2", "NB2 (Tahc)"
    elif re.search(r'\b(CDS|KN9|12SHP|DNGA|P42QR|P42V|SU2|F44|Y4L)\b', recipe_corpus, re.IGNORECASE): furnace_id, furnace_variant = "NB1", "NB1 (CDS/KN9/12SHP)"
    elif re.search(r'\bBTM\b', recipe_corpus, re.IGNORECASE): furnace_id, furnace_variant = "NB3", "NB3 (BTM)"
    elif re.search(r'\b(KE8|M2|EVO|NB3)\b', recipe_corpus, re.IGNORECASE): furnace_id, furnace_variant = "NB3", "NB3 (KE8 : M2/EVO)"
    elif (re.search(r'\bWK\d{1,2}\b', recipe_corpus, re.IGNORECASE) or re.search(r'\b\d{6}\b', recipe_corpus)): furnace_id, furnace_variant = "NB1", "NB1 (Standard)"
    else:
        f_match = re.search(r'NB\s*Furnace\s*0?([123])\b|NB\s*#?\s*0?([123])\b|NB-0?([123])\b', recipe_corpus, re.IGNORECASE)
        if f_match: 
            found_num = next(g for g in f_match.groups() if g is not None)
            furnace_id = furnace_variant = f"NB{found_num}"

    is_j4ll = bool(re.search(r'\b(J4LL)\b', recipe_corpus, re.IGNORECASE))

    if not (is_j4ll and "NB3 (KE8 : M2/EVO)" in furnace_variant):
        for col in ["PB#9", "PB#10"]:
            if col in invalid_cols:
                if col in probe_cols: probe_cols.remove(col)
                invalid_cols.remove(col)
                if col in df_master.columns: df_master.drop(columns=[col], inplace=True)

    # Note: Simplified probe mappings mapping for brevity here.
    max_probe_idx = 10 if (is_j4ll and "NB3 (KE8 : M2/EVO)" in furnace_variant) else max([int(c.replace("PB#", "")) for c in probe_cols] + [8])
    for i in range(1, max_probe_idx + 1):
        k = f"PB#{i}"
        if k not in probe_locations:
            if i <= 8 or k in probe_cols: probe_locations[k] = f"#{i} (°C) Unlabeled"

    base_cfg = FURNACE_CONFIGS.get(furnace_id, FURNACE_CONFIGS["NB3"])
    cfg = dict(base_cfg)

    if "RAD" in furnace_variant: cfg.update({"dryer_dwell_thresh_1": 150.0, "dryer_dwell_thresh_2": 175.0, "debinder_dwell_thresh": 200.0, "brazing_dwell_thresh_1": 550.0, "brazing_dwell_thresh_2": 577.0, "brazing_dwell_thresh_3": 583.0, "brazing_dwell_thresh_4": 600.0})
    elif "NB1" in furnace_variant: cfg.update({"dryer_dwell_thresh_1": 150.0, "dryer_dwell_thresh_2": 200.0, "debinder_dwell_thresh": 300.0, "brazing_dwell_thresh_1": 550.0, "brazing_dwell_thresh_2": 577.0, "brazing_dwell_thresh_3": 591.0, "brazing_dwell_thresh_4": 600.0})
    elif "NB2" in furnace_variant: cfg.update({"dryer_dwell_thresh_1": 200.0, "dryer_dwell_thresh_2": 250.0, "debinder_dwell_thresh": None, "brazing_dwell_thresh_1": 550.0, "brazing_dwell_thresh_2": 577.0, "brazing_dwell_thresh_3": 591.0, "brazing_dwell_thresh_4": 600.0})
    elif "BTM" in furnace_variant: cfg.update({"dryer_dwell_thresh_1": 250.0, "dryer_dwell_thresh_2": 300.0, "debinder_dwell_thresh": None, "brazing_dwell_thresh_1": 550.0, "brazing_dwell_thresh_2": 577.0, "brazing_dwell_thresh_3": 591.0, "brazing_dwell_thresh_4": 600.0})
    elif "NB3" in furnace_variant: cfg.update({"dryer_dwell_thresh_1": 150.0, "dryer_dwell_thresh_2": 200.0, "debinder_dwell_thresh": None, "brazing_dwell_thresh_1": 550.0, "brazing_dwell_thresh_2": 577.0, "brazing_dwell_thresh_3": 591.0, "brazing_dwell_thresh_4": 600.0})

    line_speed_mpm = cfg["line_speed_mpm"]
    cv_sp_matches = re.findall(r'CV\s*SP\s*[:=]?\s*(\d{3,4})\s*(?:mm/\s*min|mm)?', recipe_corpus, re.IGNORECASE)
    if cv_sp_matches:
        last_speed = float(cv_sp_matches[-1])
        if 800.0 <= last_speed <= 2500.0: line_speed_mpm = last_speed / 1000.0

    df_master["Distance_Meters"] = ((df_master["Time_Seconds"] - detected_start_sec) / 60.0) * line_speed_mpm
    probe_start_info = {}
    for col in probe_cols:
        p_sec = probe_start_secs.get(col, detected_start_sec)
        offset_m = ((p_sec - detected_start_sec) / 60.0) * line_speed_mpm
        df_master[f"Distance_{col}"] = ((df_master["Time_Seconds"] - p_sec) / 60.0) * line_speed_mpm
        probe_start_info[col] = {
            "Start_Sec": p_sec,
            "Start_HHMMSS": df_master[df_master["Time_Seconds"] == p_sec].iloc[0]["Time_HHMMSS"] if p_sec < len(df_master) else "00:00:00",
            "Offset_Sec": p_sec - detected_start_sec, "Offset_Meters": round(offset_m, 2), "Is_First": (col == first_probe_name)
        }

    return {
        "filename": filename, "df_master": df_master, "probe_cols": probe_cols, "invalid_cols": invalid_cols, "furnace_id": furnace_id, "furnace_variant": furnace_variant, "cfg": cfg,
        "line_speed_mpm": line_speed_mpm, "detected_start_sec": detected_start_sec, "detected_start_hhmmss": detected_start_hhmmss, "first_probe_name": first_probe_name,
        "operator_name": operator_name, "company": company, "site": site, "operator_comment": clean_comments_text, "process_settings": process_settings,
        "probe_locations": probe_locations, "probe_start_info": probe_start_info, "embedded_img": embedded_img,
        "extracted_date": extracted_date, "extracted_time": extracted_time_str
    }

# ==============================================================================
# RECORDER .DAD / .CSV FUNCTIONS
# ==============================================================================
def check_machine_type(filenames):
    has_nb1 = False; has_nb2 = False
    for f in filenames:
        if 'DATA' in f.upper(): has_nb2 = True
        else: has_nb1 = True
    if has_nb1 and has_nb2: return 'MIXED', []
    elif has_nb2: return 'NB2', CH_NB2
    else: return 'NB1', CH_NB1

def find_dad_params(raw):
    if len(raw) < 5000: return None, None 
    max_search = min(80000, len(raw) - 1000)
    for offset in range(1000, max_search):
        yr, mo, dy, hr, mn, sc = raw[offset:offset+6]
        if 0 <= yr <= 99 and 1 <= mo <= 12 and 1 <= dy <= 31 and 0 <= hr <= 23 and 0 <= mn <= 59 and 0 <= sc <= 59:
            try:
                y_full = 2000 + yr if yr < 80 else 1900 + yr
                t1 = datetime(y_full, mo, dy, hr, mn, sc)
            except ValueError: continue
            
            for rs in range(16, 2048, 2): 
                valid_chain = True; prev_t = t1
                for step in range(1, 5):
                    check_pos = offset + (rs * step)
                    if check_pos + 6 >= len(raw):
                        valid_chain = False; break
                    y2, m2, d2, h2, min2, s2 = raw[check_pos:check_pos+6]
                    if not (0 <= y2 <= 99 and 1 <= m2 <= 12 and 1 <= d2 <= 31 and 0 <= h2 <= 23 and 0 <= min2 <= 59 and 0 <= s2 <= 59):
                        valid_chain = False; break
                    try:
                        y2_f = 2000 + y2 if y2 < 80 else 1900 + y2
                        t2 = datetime(y2_f, m2, d2, h2, min2, s2)
                        delta = (t2 - prev_t).total_seconds()
                        if not (0 < delta <= 3600):
                            valid_chain = False; break
                        prev_t = t2
                    except ValueError:
                        valid_chain = False; break
                if valid_chain: return offset, rs
    return None, None 

def parse_dad(raw: bytes, active_channels) -> list:
    records = []
    offset, record_size = find_dad_params(raw)
    if offset is None or record_size is None: return records 
    bpc = 4 if record_size >= 70 else 2
    body_len = len(raw) - offset
    if body_len <= 0: return records
    total = body_len // record_size
    
    for i in range(total):
        base = offset + i * record_size
        hdr  = raw[base:base+8]
        if len(hdr) < 8: break
        yr, mo, dy, hr, mn, sc = hdr[0], hdr[1], hdr[2], hdr[3], hdr[4], hdr[5]
        if not (0 <= yr <= 99 and 1 <= mo <= 12 and 1 <= dy <= 31 and 0 <= hr <= 23 and 0 <= mn <= 59 and 0 <= sc <= 59): continue
        parsed_yr = (2000 + yr) if yr < 80 else (1900 + yr)
        try: ts = datetime(parsed_yr, mo, dy, hr, mn, sc)
        except ValueError: continue
            
        rec = {'ts': ts}
        for ch, name, unit in active_channels:
            ch_idx = int(ch.replace('CH', '')) - 1
            data_pos = base + 8 + (ch_idx * bpc)
            if data_pos + 2 > base + record_size: 
                rec[f'{ch}_min'] = rec[f'{ch}_max'] = rec[f'{ch}_avg'] = rec[ch] = None
                continue
            
            v1 = struct.unpack_from('>h', raw, data_pos)[0]
            if bpc == 4 and data_pos + 4 <= base + record_size:
                v2 = struct.unpack_from('>h', raw, data_pos + 2)[0]
                min_v, max_v = min(v1, v2), max(v1, v2)
            else: min_v = max_v = v1
            
            divisor = 1.0 if name == 'N2 .1' else 10.0
            if v1 not in (-32768, -32767, 32767, 32766) and (-32000 < v1 < 32000):
                min_val, max_val = min_v / divisor, max_v / divisor
                if -1000.0 <= min_val <= 10000.0 and -1000.0 <= max_val <= 10000.0:
                    rec[f'{ch}_min'], rec[f'{ch}_max'], rec[f'{ch}_avg'], rec[ch] = round(min_val, 1), round(max_val, 1), round((min_val + max_val) / 2.0, 1), round((min_val + max_val) / 2.0, 1)
                else: rec[f'{ch}_min'] = rec[f'{ch}_max'] = rec[f'{ch}_avg'] = rec[ch] = None
            else: rec[f'{ch}_min'] = rec[f'{ch}_max'] = rec[f'{ch}_avg'] = rec[ch] = None
        records.append(rec)
    return records

@st.cache_data(show_spinner=False)
def process_dad_files(files_d, mode_k, act_channels):
    all_records = []
    for fname, raw in files_d:
        recs = parse_dad(raw, act_channels)
        if len(recs) > 10: all_records.extend(recs[3:-2])
        else: all_records.extend(recs)
    if not all_records: return []
    all_records.sort(key=lambda x: x['ts'])
    if len(all_records) > 0:
        streaks = []
        current_streak = [all_records[0]]
        for i in range(1, len(all_records)):
            if (all_records[i]['ts'] - all_records[i-1]['ts']).total_seconds() <= 86400 * 2: current_streak.append(all_records[i])
            else:
                streaks.append(current_streak)
                current_streak = [all_records[i]]
        streaks.append(current_streak)
        all_records = max(streaks, key=len)
    seen = set(); unique = []
    for r in all_records:
        k = r['ts']
        if k not in seen:
            seen.add(k)
            new_r = {'ts': k}
            for ch,_,_ in act_channels: new_r[ch] = r.get(f'{ch}{mode_k}')
            unique.append(new_r)
    df = pd.DataFrame(unique)
    if not df.empty:
        df.set_index('ts', inplace=True)
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            df[col] = df[col].rolling(window=3, min_periods=1, center=True).median()
        df = df.reset_index()
        unique = df.where(pd.notnull(df), None).to_dict('records')
    return unique

def parse_debinder_csv(file_path_or_buffer):
    try:
        if isinstance(file_path_or_buffer, str):
            with open(file_path_or_buffer, "r", encoding="utf-8", errors="ignore") as f: raw_bytes = f.read().encode("utf-8")
        else:
            file_path_or_buffer.seek(0)
            raw_bytes = file_path_or_buffer.read()
        text_content = None
        for enc in ['cp932', 'shift_jis', 'utf-8', 'tis-620', 'latin1']:
            try:
                text_content = raw_bytes.decode(enc)
                break
            except Exception: continue
        if text_content is None: text_content = raw_bytes.decode('utf-8', errors='ignore')
        
        text_upper = text_content.upper()
        if "COMBUS" not in text_upper and "DEBINDER" not in text_upper: return pd.DataFrame()
        if "#ENDHEADER" in text_upper: return pd.DataFrame()
            
        lines = text_content.splitlines()
        parsed_rows = []
        for line in lines:
            line_str = line.strip()
            if "," in line_str:
                parts = [p.strip() for p in line_str.split(",")]
                if len(parts) >= 6 and re.search(r'\d', parts[0]):
                    try:
                        dt_val = parts[0].replace('"', '')
                        if len(parts) >= 17: z1, z2, z3, z4, comb = float(parts[2].replace('"', '')), float(parts[5].replace('"', '')), float(parts[8].replace('"', '')), float(parts[11].replace('"', '')), float(parts[14].replace('"', ''))
                        else: z1, z2, z3, z4, comb = float(parts[1].replace('"', '')), float(parts[2].replace('"', '')), float(parts[3].replace('"', '')), float(parts[4].replace('"', '')), float(parts[5].replace('"', ''))
                        parsed_rows.append({"DateTime": dt_val, "Zone #1": z1, "Zone #2": z2, "Zone #3": z3, "Zone #4": z4, "Combustion Air Temp": comb})
                    except ValueError: continue
        if not parsed_rows: return pd.DataFrame()
        df = pd.DataFrame(parsed_rows)
        df["DateTime"] = pd.to_datetime(df["DateTime"], errors="coerce")
        return df.dropna(subset=["DateTime"]).reset_index(drop=True)
    except Exception as e: return pd.DataFrame()

def process_debinder_files(uploaded_files, expected_furnace=None):
    combined_dfs, invalid_files = [], []
    for file in uploaded_files:
        df_single = parse_debinder_csv(file)
        if df_single is None or df_single.empty: invalid_files.append(file.name)
        else: combined_dfs.append(df_single)
        
    if invalid_files:
        if expected_furnace: st.error(f"❌ **ไฟล์ไม่ถูกต้อง!** ตรวจพบไฟล์ที่ไม่ใช่ข้อมูล Debinder ของเตา {expected_furnace}: {', '.join(invalid_files)}\n\nกรุณากดปุ่ม Clear Data และอัปโหลดไฟล์ให้ตรงกับเตาหลัก")
        else: st.error(f"❌ **ไฟล์ไม่ถูกต้อง!** ตรวจพบไฟล์ที่ไม่ใช่รูปแบบของ NB1 Debinder CSV: {', '.join(invalid_files)}")
        st.stop()
        
    if not combined_dfs: return pd.DataFrame()
    full_df = pd.concat(combined_dfs, ignore_index=True)
    full_df = full_df.drop_duplicates(subset=["DateTime"]).sort_values("DateTime").reset_index(drop=True)
    return full_df

def extract_csv_start_time(df, condition_cols, threshold=60.0, sustained_duration=5):
    if df is None or df.empty or not condition_cols: return None
    condition = df[condition_cols].ge(threshold).any(axis=1)
    rolling_sum = condition.rolling(window=sustained_duration, min_periods=sustained_duration).sum()
    start_indices = rolling_sum[rolling_sum == sustained_duration].index
    if len(start_indices) > 0:
        first_sustained_idx = start_indices[0] - (sustained_duration - 1)
        return df.loc[first_sustained_idx, "DateTime"]
    return None

def parse_nb3_csv(uploaded_file):
    uploaded_file.seek(0)
    raw_bytes = uploaded_file.read()
    text_content = None
    for enc in ['cp932', 'shift_jis', 'utf-8-sig', 'utf-8', 'tis-620', 'latin1']:
        try:
            text_content = raw_bytes.decode(enc)
            break
        except UnicodeDecodeError: continue
    if text_content is None: text_content = raw_bytes.decode('utf-8', errors='ignore')
    
    lines = text_content.splitlines()
    endheader_cols = []
    for line in lines[:150]:
        line_str = line.strip()
        if line_str.startswith("#EndHeader"):
            endheader_cols = [x.strip() for x in line_str.split(",")]
            break
            
    header_str = " ".join(endheader_cols) if endheader_cols else text_content[:10000]
    has_top_z6_z7 = bool(re.search(r'1\)TH_CH6', header_str, re.I)) and bool(re.search(r'1\)TH_CH7', header_str, re.I))
    has_bot_z6_z7 = bool(re.search(r'2\)TH_CH6', header_str, re.I)) and bool(re.search(r'2\)TH_CH7', header_str, re.I))
    if not (has_top_z6_z7 or has_bot_z6_z7): return None

    data_rows = []
    date_regex = re.compile(r'^\d{1,4}[-/]\d{1,2}[-/]\d{1,4}')
    time_regex = re.compile(r'^\d{1,2}:\d{2}:\d{2}')
    curr_date = ""
    for line in lines:
        line_str = line.strip()
        if not line_str or line_str.startswith("#EndHeader"): continue
        if date_regex.match(line_str) and "," not in line_str:
            curr_date = line_str; continue
        parts = [p.strip() for p in line_str.split(",")]
        if date_regex.search(parts[0]): data_rows.append(parts)
        elif time_regex.search(parts[0]):
            dt_str = f"{curr_date} {parts[0]}".strip() if curr_date else parts[0]
            data_rows.append([dt_str] + parts[1:])
            
    if not data_rows: return pd.DataFrame()
    data_df = pd.DataFrame(data_rows)

    def find_col_by_keyword(key_pattern):
        if endheader_cols:
            for c_idx, name in enumerate(endheader_cols):
                if re.search(key_pattern, name, re.IGNORECASE): return c_idx
        return None

    df = pd.DataFrame()
    df["DateTime"] = pd.to_datetime(data_df[0].astype(str).str.strip(), errors="coerce", dayfirst=True)
    
    def extract_series(col_idx, fallback_idx, min_val=-200.0, max_val=10000.0):
        target_idx = col_idx if col_idx is not None else fallback_idx
        if target_idx is not None and target_idx < data_df.shape[1]:
            s = pd.to_numeric(data_df[target_idx], errors="coerce")
            return s.apply(lambda x: x if (pd.notna(x) and min_val <= x <= max_val) else None)
        return pd.Series([None] * len(data_df))

    for i in range(1, 8): df[f"Top Zone #{i}"] = extract_series(find_col_by_keyword(rf'1\)TH_CH{i}Max'), 2 + (i - 1) * 3, min_val=0.0, max_val=1200.0)
    for i in range(1, 8): df[f"Bottom Zone #{i}"] = extract_series(find_col_by_keyword(rf'2\)TH_CH{i}Max'), 2 + (7 + i - 1) * 3, min_val=0.0, max_val=1200.0)
    dryoff_names = ["DRYOFF1", "DRYOFF2", "DRYOFF3"]
    for i in range(1, 4): df[dryoff_names[i-1]] = extract_series(find_col_by_keyword(rf'3\)TH_CH{i}Max'), 2 + (14 + i - 1) * 3, min_val=0.0, max_val=1000.0)
        
    df["Oxygen EXIT"] = extract_series(find_col_by_keyword(r'3\)TH_CH4Max'), 2 + (17) * 3, min_val=0.0, max_val=2000.0)
    df["Oxygen ENTRANCE"] = extract_series(find_col_by_keyword(r'3\)TH_CH5Max'), 2 + (18) * 3, min_val=0.0, max_val=2000.0)
    df["N2 Exit"] = extract_series(find_col_by_keyword(r'3\)TH_CH7Max'), 2 + (20) * 3, min_val=0.0, max_val=20000.0)
    df["N2 Entrance"] = extract_series(find_col_by_keyword(r'3\)TH_CH8Max'), 2 + (21) * 3, min_val=0.0, max_val=20000.0)
    df["COOL WATER TEMP"] = extract_series(find_col_by_keyword(r'3\)TH_CH6Max'), 2 + (19) * 3, min_val=-200.0, max_val=1000.0)

    return df.dropna(subset=["DateTime"]).reset_index(drop=True)

def process_nb3_files(uploaded_files, expected_furnace=None):
    combined_dfs, invalid_files = [], []
    for file in uploaded_files:
        single_df = parse_nb3_csv(file)
        if single_df is None or single_df.empty: invalid_files.append(file.name)
        else: combined_dfs.append(single_df)
        
    if invalid_files:
        if expected_furnace: st.error(f"❌ **ไฟล์ไม่ถูกต้อง!** ตรวจพบไฟล์ที่ไม่ใช่ข้อมูลของเตา {expected_furnace}: {', '.join(invalid_files)}\n\nกรุณากดปุ่ม Clear Data และอัปโหลดไฟล์ให้ตรงกับเตาหลัก")
        else: st.error(f"❌ **ไฟล์ไม่ถูกต้อง!** ตรวจพบไฟล์ที่ไม่ใช่รูปแบบของ RECORDER NB3: {', '.join(invalid_files)}")
        st.stop()
        
    if not combined_dfs: return pd.DataFrame()
    full_df = pd.concat(combined_dfs, ignore_index=True)
    full_df = full_df.drop_duplicates(subset=["DateTime"]).sort_values("DateTime").reset_index(drop=True)
    return full_df

# ==============================================================================
# PLOTTING & UI RENDERERS
# ==============================================================================
def render_single_chart(data, ch_list, colors_ref, title, y_range, y_title, hline=None, std_min=None, std_max=None):
    if not ch_list: return None
    fig = go.Figure()
    ts = [r['ts'] for r in data]
    for i, (ch, name, unit) in enumerate(ch_list):
        color = colors_ref[i] if isinstance(colors_ref, list) else colors_ref.get(ch, '#888')
        fig.add_trace(go.Scatter(x=ts, y=[r.get(ch) for r in data], name=name, mode='lines', line=dict(color=color, width=1.5), hovertemplate=f'<b>{name}</b>: %{{y:.1f}} {unit}<extra></extra>' if unit else f'<b>{name}</b>: %{{y:.1f}}<extra></extra>'))
    
    if std_min is not None and std_max is not None:
        fig.add_trace(go.Scatter(x=[ts[0], ts[-1]], y=[std_max, std_max], name=f"Std Max ({std_max})", mode='lines', line=dict(color="red", width=1.5, dash="dash"), visible=True))
        fig.add_trace(go.Scatter(x=[ts[0], ts[-1]], y=[std_min, std_min], name=f"Std Min ({std_min})", mode='lines', line=dict(color="blue", width=1.5, dash="dash"), visible=True))
        
    if hline is not None:
        fig.add_hline(y=hline, line_dash="dash", line_color="#FF4B4B", line_width=1.5, annotation_text=f"Standard {hline} {y_title}", annotation_position="bottom right", annotation_font=dict(color="#FF4B4B", size=12))
    fig.update_layout(title=dict(text=title, font=dict(size=18, weight="bold")), height=450, hovermode='x unified', hoverlabel=dict(font_size=12, namelength=30), legend=dict(title="Channels", orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.02, font=dict(size=12), itemsizing='constant'), margin=dict(l=60, r=150, t=60, b=40))
    if y_range: fig.update_layout(yaxis=dict(range=y_range, title_text=y_title, title_font=dict(size=14)))
    else: fig.update_layout(yaxis=dict(title_text=y_title, title_font=dict(size=14)))
    fig.update_xaxes(tickformat='%d/%m\n%H:%M', tickfont=dict(size=11), showticklabels=True)
    return fig

def render_dual_axis_chart(data, ch_left, ch_right, colors_left, colors_right, title, y1_range, y1_title, y2_title, hline_left=None, y2_range=None):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    ts = [r['ts'] for r in data]
    for i, (ch, name, unit) in enumerate(ch_left):
        color = colors_left[i] if isinstance(colors_left, list) else colors_left.get(ch, '#888')
        fig.add_trace(go.Scatter(x=ts, y=[r.get(ch) for r in data], name=name, mode='lines', line=dict(color=color, width=1.5), hovertemplate=f'<b>{name}</b>: %{{y:.1f}} {unit}<extra></extra>' if unit else f'<b>{name}</b>: %{{y:.1f}}<extra></extra>'), secondary_y=False)
    for i, (ch, name, unit) in enumerate(ch_right):
        color = colors_right[i] if isinstance(colors_right, list) else colors_right.get(ch, '#888')
        fig.add_trace(go.Scatter(x=ts, y=[r.get(ch) for r in data], name=name, mode='lines', line=dict(color=color, width=1.5, dash='dot'), hovertemplate=f'<b>{name}</b>: %{{y:.0f}} {unit}<extra></extra>' if unit else f'<b>{name}</b>: %{{y:.0f}}<extra></extra>'), secondary_y=True)
    if hline_left is not None:
        fig.add_hline(y=hline_left, line_dash="dash", line_color="#FF4B4B", line_width=1.5, annotation_text=f"Standard {hline_left} {y1_title.split()[0]}", annotation_position="bottom right", annotation_font=dict(color="#FF4B4B", size=12), secondary_y=False)
    fig.update_layout(title=dict(text=title, font=dict(size=18, weight="bold")), height=450, hovermode='x unified', hoverlabel=dict(font_size=12, namelength=30), legend=dict(title="Channels", orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.08, font=dict(size=12), itemsizing='constant'), margin=dict(l=60, r=180, t=60, b=40))
    if y1_range: fig.update_layout(yaxis=dict(range=y1_range, title_text=y1_title, title_font=dict(size=14)))
    if y2_range: fig.update_layout(yaxis2=dict(range=y2_range, title_text=y2_title, title_font=dict(size=14), showgrid=False))
    fig.update_xaxes(tickformat='%d/%m\n%H:%M', tickfont=dict(size=11), showticklabels=True)
    return fig

def apply_industrial_style(fig, y_title, y_range=None, is_dual_axis=False, std_min=None, std_max=None, ts=None):
    layout_args = dict(
        hovermode="x unified", showlegend=True,
        legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02),
        xaxis=dict(title=dict(text="Date & Time"), showgrid=True, type="date"),
        yaxis=dict(title=dict(text=y_title), showgrid=True, zeroline=False),
        height=450, margin=dict(l=60, r=180, t=30, b=40),
    )
    if y_range and not is_dual_axis: layout_args["yaxis"]["range"] = y_range
    fig.update_layout(**layout_args)
    if std_min is not None and std_max is not None and ts is not None and len(ts) > 0:
        fig.add_trace(go.Scatter(x=[ts.iloc[0], ts.iloc[-1]], y=[std_max, std_max], name=f"Std Max ({std_max})", mode='lines', line=dict(color="red", width=1.5, dash="dash"), visible=True))
        fig.add_trace(go.Scatter(x=[ts.iloc[0], ts.iloc[-1]], y=[std_min, std_min], name=f"Std Min ({std_min})", mode='lines', line=dict(color="blue", width=1.5, dash="dash"), visible=True))

def add_paq_overlay(fig, df_paq, probe_cols, invalid_cols, is_dual_axis=False):
    for col in probe_cols:
        if col not in invalid_cols:
            trace = go.Scatter(x=df_paq["Sync_DateTime"], y=df_paq[col], name=f"PAQ: {col}", mode="lines", line=dict(color=PROBE_COLORS.get(col, "#ffffff"), width=2.5), opacity=0.9)
            if is_dual_axis: fig.add_trace(trace, secondary_y=False)
            else: fig.add_trace(trace)
    return fig

def add_zone_backgrounds(fig, zones, paq_start_dt, detected_start_sec, line_speed_mpm):
    if line_speed_mpm <= 0: return fig
    for z in zones:
        z_color = GROUP_COLORS.get(z["group"], "rgba(200, 200, 200, 0.2)")
        z_start_sec = detected_start_sec + (z["start"] / line_speed_mpm) * 60
        z_end_sec = detected_start_sec + ((z["start"] + z["length"]) / line_speed_mpm) * 60
        z_start_time = paq_start_dt + pd.to_timedelta(z_start_sec, unit="s")
        z_end_time = paq_start_dt + pd.to_timedelta(z_end_sec, unit="s")
        fig.add_vrect(x0=z_start_time, x1=z_end_time, fillcolor=z_color, layer="below", line_width=0.5, line_dash="dot", line_color="rgba(120, 120, 120, 0.4)", annotation_text=f"{z['num']}.{z['name']}", annotation_position="top left", annotation=dict(font_size=9, font_color="#a0aab2", textangle=-90))
    return fig

def render_combined_charts_vertically(charts_list, zoom_mode_selection, zoom_range, key_prefix):
    if not charts_list: return
    for i, c in enumerate(charts_list):
        st.markdown(f"#### {c['title']}")
        fig = c["fig"]
        if zoom_mode_selection == "ซูมอัตโนมัติทุกกราฟ (Auto-Zoom All)": fig.update_xaxes(range=zoom_range)
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("---")

def to_excel_bytes(dataframe):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_export = dataframe.copy()
        for col in df_export.select_dtypes(include=['datetime64[ns, UTC]', 'datetime64[ns]']).columns:
            df_export[col] = df_export[col].dt.strftime('%Y-%m-%d %H:%M:%S')
        df_export.to_excel(writer, index=False)
    output.seek(0)
    return output.getvalue()


# ==============================================================================
# STREAMLIT UI MAIN LAYOUT
# ==============================================================================
if "paq1_uploader_key" not in st.session_state: st.session_state.paq1_uploader_key = 0
if "paq2_uploader_key" not in st.session_state: st.session_state.paq2_uploader_key = 0
if "recorder_uploader_key" not in st.session_state: st.session_state.recorder_uploader_key = 0
if "file_uploader_key" not in st.session_state: st.session_state["file_uploader_key"] = str(datetime.now().timestamp())

st.title("🔥 Datapaq .PAQ Furnace Profiler & Analyzer")
st.markdown("Automated thermal profile extraction, zone metrics, and multi-file comparison.")

with st.sidebar:
    st.header("📁 1. Upload PAQ File")
    st.caption("อัปโหลดเพื่อใช้ประมวลผลกราฟ, เปรียบเทียบ หรืออ้างอิงเป็นเตาหลักใน Simulation")
    if st.button("🔄 Reset / Clear Data"):
        st.cache_data.clear()
        st.session_state.paq1_uploader_key += 1
        st.session_state.paq2_uploader_key += 1
        st.session_state.recorder_uploader_key += 1
        st.session_state.file_uploader_key = str(datetime.now().timestamp())
        st.rerun()
        
    uploaded_file1 = st.file_uploader("Upload Main .PAQ File", type=["paq"], key=f"paq1_{st.session_state.paq1_uploader_key}")

    data1 = None
    current_nb_detected_paq = None
    if uploaded_file1:
        with st.spinner("Processing Datapaq file..."):
            data1 = process_paq_file(uploaded_file1.getvalue(), uploaded_file1.name)
            current_nb_detected_paq = identify_furnace_type(uploaded_file1.name)
        if not data1:
            st.error("❌ Failed to parse valid probe temperature streams from the uploaded file.")

# ==============================================================================
# TABS DECLARATION
# ==============================================================================
tabs = st.tabs([
    "📊 Profile Graphs & Analysis", 
    "⚖ Compare Files", 
    "🔗 Recorder Data (Standalone / Combine)",
    "🏭 Furnace Product & Simulation"
])

# ---------------------------------------------------------
# TAB 0: PROFILE GRAPHS & ANALYSIS
# ---------------------------------------------------------
with tabs[0]:
    if not data1:
        st.markdown('<div class="custom-warning-box">⚠️ <b>กรุณาอัปโหลดไฟล์หลัก (.PAQ) ที่แถบด้านซ้ายมือก่อน!</b> ระบบจำเป็นต้องใช้ข้อมูลเพื่อแสดงผลกราฟและวิเคราะห์ครับ</div>', unsafe_allow_html=True)
    else:
        df_m1, f_variant, cfg = data1["df_master"], data1["furnace_variant"], data1["cfg"]
        zones, probe_cols, invalid_cols = data1["cfg"]["zones"], data1["probe_cols"], data1["invalid_cols"]
        total_furnace_length = zones[-1]["start"] + zones[-1]["length"] if zones else 0
        furnace_duration_mins = total_furnace_length / data1['line_speed_mpm'] if data1['line_speed_mpm'] else 0
        furnace_duration_secs = int(furnace_duration_mins * 60)
        furnace_id = data1["furnace_id"]

        st.success(f"✓ File Loaded Successfully: **{data1['filename']}**")
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        m_col1.metric("Confirmed Furnace", f_variant)
        m_col2.metric("Conveyor Speed", f"{data1['line_speed_mpm']:.3f} m/min")
        m_col3.metric("Entry Time", f"{data1['detected_start_hhmmss']}")
        
        process_hh = furnace_duration_secs // 3600
        process_mm = (furnace_duration_secs % 3600) // 60
        process_ss = furnace_duration_secs % 60
        process_time_str = f"{int(process_hh):02d}:{int(process_mm):02d}:{int(process_ss):02d}"
        m_col4.metric("Process PAQ Time", process_time_str)

        st.subheader("Global Furnace Profile")
        fig1 = go.Figure()
        base_date = pd.Timestamp("1970-01-01 00:00:00")
        d_max_view = total_furnace_length + 1.0 
        t_max_view = data1['detected_start_sec'] + (d_max_view / data1['line_speed_mpm'] * 60) if data1['line_speed_mpm'] else 0
        t_min = df_m1["Time_Seconds"].min()
        t_max = min(df_m1["Time_Seconds"].max(), t_max_view)
        d_min = df_m1["Distance_Meters"].min()
        d_max = min(df_m1["Distance_Meters"].max(), d_max_view)

        custom_hover1 = np.stack((df_m1["Time_HHMMSS"], df_m1["Time_Seconds"], df_m1["Distance_Meters"]), axis=-1)
        for col in probe_cols:
            legend_name = f"<span style='color:gray'>{col}</span>" if col in invalid_cols else col
            fig1.add_trace(go.Scatter(x=df_m1["Time_Stamp"], y=df_m1[col], mode="lines", name=legend_name, customdata=custom_hover1, hovertemplate=f"{col}: %{{y:.1f}} °C<br>Time: %{{customdata[0]}}<br>Dist: %{{customdata[2]:.2f}} m", line=dict(color=PROBE_COLORS.get(col)), xaxis="x"))
            
        for z in zones:
            z_color = GROUP_COLORS.get(z["group"], "rgba(200, 200, 200, 0.2)")
            z_start_sec = (z["start"] / data1['line_speed_mpm']) * 60 + data1['detected_start_sec']
            z_end_sec = ((z["start"] + z["length"]) / data1['line_speed_mpm']) * 60 + data1['detected_start_sec']
            z_start_time = base_date + pd.to_timedelta(z_start_sec, unit="s")
            z_end_time = base_date + pd.to_timedelta(z_end_sec, unit="s")
            fig1.add_vrect(x0=z_start_time, x1=z_end_time, fillcolor=z_color, layer="below", line_width=0.5, line_dash="dot", line_color="rgba(120, 120, 120, 0.4)", annotation_text=f"{z['num']}.{z['name']}", annotation_position="top left", annotation=dict(font_size=9, font_color="#a0aab2", textangle=-90))
            
        fig1.add_hline(y=cfg["trigger_temp_brazing"], line_dash="dash", line_color="red", annotation_text=f"Brazing ({cfg['trigger_temp_brazing']}°C)", annotation_position="bottom right")

        fig1.update_layout(
            title=f"GLOBAL FURNACE PROFILE ({f_variant}): {data1['filename']}", yaxis=dict(title="Temperature (°C)", domain=[0.15, 1.0]), hovermode="x unified", template="plotly_white", height=600, margin=dict(b=80),
            xaxis=dict(title="Time (hh:mm:ss)", tickformat="%H:%M:%S", range=[base_date + pd.to_timedelta(t_min, unit="s"), base_date + pd.to_timedelta(t_max, unit="s")], anchor="y"),
            xaxis2=dict(title="Distance (Meters)", overlaying="x", side="bottom", position=0.0, anchor="free", range=[d_min, d_max])
        )
        fig1.add_trace(go.Scatter(x=df_m1["Distance_Meters"], y=df_m1[probe_cols[0]] * 0, showlegend=False, opacity=0, xaxis="x2", hoverinfo='skip'))
        st.plotly_chart(fig1, use_container_width=True)
        st.markdown("---")

        stages = cfg.get("stages", [])
        has_debinder = any(s["Stage"] == "Debinder" for s in stages)
        dryer_info = next((s for s in stages if s["Stage"] == "Dryer"), stages[0] if stages else None)
        debinder_info = next((s for s in stages if s["Stage"] == "Debinder"), None) if has_debinder else None
        brazing_info = next((s for s in stages if s["Stage"] == "Brazing"), stages[-1] if stages else None)

        process_time = df_m1["Time_Seconds"] - data1["detected_start_sec"]
        
        if "NB1" in f_variant:
            dryer_max_df = df_m1[(process_time >= 0) & (process_time <= 300)]
            dryer_dwell_df = dryer_max_df.copy()
            debinder_df = df_m1[(process_time > 300) & (process_time <= 930)] if has_debinder else None
        elif "NB2" in f_variant:
            dryer_max_df = df_m1[(process_time >= 0) & (process_time <= 270)]
            dryer_dwell_df = dryer_max_df.copy()
            debinder_df = None
        elif f_variant == "NB3 (KE8 : M2/EVO)":
            dryer_max_df = df_m1[(process_time >= 0) & (process_time <= 270)]
            dryer_dwell_df = dryer_max_df.copy()
            debinder_df = df_m1[(df_m1["Distance_Meters"] >= debinder_info["Start (m)"]) & (df_m1["Distance_Meters"] <= debinder_info["End (m)"])] if debinder_info else None
        else:
            dryer_max_df = df_m1[(df_m1["Distance_Meters"] >= dryer_info["Start (m)"]) & (df_m1["Distance_Meters"] <= dryer_info["End (m)"])] if dryer_info else pd.DataFrame()
            dryer_dwell_df = dryer_max_df.copy()
            debinder_df = df_m1[(df_m1["Distance_Meters"] >= debinder_info["Start (m)"]) & (df_m1["Distance_Meters"] <= debinder_info["End (m)"])] if debinder_info else None
            
        brazing_df = df_m1[(df_m1["Distance_Meters"] >= brazing_info["Start (m)"]) & (df_m1["Distance_Meters"] <= brazing_info["End (m)"])] if brazing_info else pd.DataFrame()

        matrix_rows = []
        for col in probe_cols:
            if col in invalid_cols:
                r = {"Probe": col}
                r["Brazing Max (°C)"] = "***"
                for bt in [cfg.get(f"brazing_dwell_thresh_{i}") for i in range(1, 5)]:
                    if bt is not None: r[f"Brazing Dwell (≥{int(bt)}°C)"] = "***"
                if has_debinder and debinder_df is not None:
                    d_thresh = cfg.get("debinder_dwell_thresh", 300.0) or 300.0
                    r["Debinder Max (°C)"] = "***"
                    r[f"Debinder Dwell (≥{int(d_thresh)}°C)"] = "***"
                r["Dryer Max (°C)"] = "***"
                for dt in [cfg.get("dryer_dwell_thresh_1"), cfg.get("dryer_dwell_thresh_2")]:
                    if dt is not None: r[f"Dryer Dwell (≥{int(dt)}°C)"] = "***"
                matrix_rows.append(r)
                continue

            r = {"Probe": col}
            bz_max = brazing_df[col].max() if not brazing_df.empty else np.nan
            r["Brazing Max (°C)"] = f"{bz_max:.1f}" if pd.notna(bz_max) else "N/A"
            for bt in [cfg.get(f"brazing_dwell_thresh_{i}") for i in range(1, 5)]:
                if bt is not None: r[f"Brazing Dwell (≥{int(bt)}°C)"] = format_dwell_time((brazing_df[col] >= bt).sum()) if not brazing_df.empty else "00:00:00"

            if has_debinder and debinder_df is not None:
                d_thresh = cfg.get("debinder_dwell_thresh", 300.0) or 300.0
                db_max = debinder_df[col].max()
                r["Debinder Max (°C)"] = f"{db_max:.1f}" if pd.notna(db_max) else "N/A"
                r[f"Debinder Dwell (≥{int(d_thresh)}°C)"] = format_dwell_time((debinder_df[col] >= d_thresh).sum()) if not debinder_df.empty else "00:00:00"

            d_max = dryer_max_df[col].max() if not dryer_max_df.empty else np.nan
            r["Dryer Max (°C)"] = f"{d_max:.1f}" if pd.notna(d_max) else "N/A"
            for dt in [cfg.get("dryer_dwell_thresh_1"), cfg.get("dryer_dwell_thresh_2")]:
                if dt is not None: r[f"Dryer Dwell (≥{int(dt)}°C)"] = format_dwell_time((dryer_dwell_df[col] >= dt).sum()) if not dryer_dwell_df.empty else "00:00:00"
            matrix_rows.append(r)
            
        if f_variant == "NB1 (RAD)":
            desired_order = ["PB#1", "PB#2", "PB#3", "PB#8", "PB#4", "PB#5", "PB#6", "PB#7"]
            matrix_rows = sorted(matrix_rows, key=lambda x: desired_order.index(x["Probe"]) if x["Probe"] in desired_order else 99)

        st.subheader(f"⏱ Inspection Matrix — {f_variant}")
        std_info = STANDARD_SPECS.get(f_variant)
        if std_info:
            st.markdown(f"""
            <div style="background-color: rgba(38, 39, 48, 0.8); padding: 10px; border-left: 5px solid #00ffff; border-radius: 5px; margin-bottom: 15px;">
                <strong style="color: #00ffff; font-size: 1.1rem;">📝 Standard: {std_info['id']}</strong><br>
                <span style="color: #a0aab2; font-size: 0.9rem;"><b>Max Temp:</b> {std_info['max']}<br><b>Dwell Time:</b> {std_info['dwell']}</span>
            </div>
            """, unsafe_allow_html=True)
            
        st.markdown("""
        <div style="font-size: 0.95rem; margin-bottom: 10px; padding: 10px; border-radius: 5px; background-color: rgba(255,255,255,0.05);">
            <b>Color Legend / คำอธิบายสี:</b>&nbsp;&nbsp;
            <span style="color: #009900; font-weight: bold;">■ Green (สีเขียว)</span>: Pass standard (ผ่านเกณฑ์) &nbsp;&nbsp;|&nbsp;&nbsp;
            <span style="color: #d32f2f; font-weight: bold;">■ Red (สีแดง)</span>: Fail standard (ไม่ผ่านเกณฑ์) &nbsp;&nbsp;|&nbsp;&nbsp;
            <span style="font-weight: bold; opacity: 0.7;">■ Default (สีปกติ)</span>: Reference only (ใช้เพื่ออ้างอิง)
        </div>
        """, unsafe_allow_html=True)

        matrix_placeholder = st.empty()
        check_dryer = st.checkbox("🔍 ตรวจสอบเกณฑ์ Dryer Max Temp & Dwell Time / Evaluate Dryer Max & Dwell", value=False)
        df_matrix = pd.DataFrame(matrix_rows)
        matrix_placeholder.dataframe(df_matrix.style.apply(style_inspection_matrix, variant=f_variant, check_dryer_max=check_dryer, axis=1), use_container_width=True, hide_index=True)
        
        overall_pass = True
        failed_points = []
        val_rules = VALIDATION_RULES.get(f_variant, {})
        for r in matrix_rows:
            probe = r["Probe"]
            if probe in invalid_cols: continue
            for k, v in r.items():
                if k == "Probe": continue
                if not check_dryer and ("Dryer Max" in k or "Dryer Dwell" in k): continue 
                rule = val_rules.get(k)
                if f_variant == "NB1 (CDS/KN9/12SHP)" and k == "Brazing Dwell (≥577°C)":
                    rule = (240, 465) if probe in ["PB#1", "PB#5"] else (120, 465)
                if not rule: continue
                is_fail = False
                if pd.isna(v) or v == "00:00:00" or v == "" or v == 0 or v == "N/A":
                    if rule[0] > 0: is_fail = True
                else:
                    min_v, max_v = rule
                    if "Max (°C)" in k:
                        try:
                            if not (min_v <= float(v) <= max_v): is_fail = True
                        except: pass
                    elif "Dwell" in k:
                        try:
                            parts = str(v).split(':')
                            if len(parts) == 3:
                                total_s = int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
                                if not (min_v <= total_s <= max_v): is_fail = True
                        except: pass
                if is_fail:
                    overall_pass = False
                    failed_points.append(f"{probe} ({k})")

        if std_info:
            if overall_pass: st.success("✅ **OVERALL STATUS: PASS | สถานะภาพรวม: ผ่านเกณฑ์มาตรฐาน**\n\nThe thermal profile meets all specified requirements for this product. (โปรไฟล์อุณหภูมิผ่านข้อกำหนดทั้งหมดสำหรับผลิตภัณฑ์นี้)")
            else:
                fail_str = ", ".join(list(dict.fromkeys(failed_points)))
                st.error(f"❌ **OVERALL STATUS: FAIL | สถานะภาพรวม: ไม่ผ่านเกณฑ์มาตรฐาน**\n\nThe thermal profile does NOT meet the requirements. Please check the red values in the matrix. (โปรไฟล์อุณหภูมิไม่ผ่านข้อกำหนด กรุณาตรวจสอบค่าสีแดงในตาราง)\n\n**Failed Items (จุดที่ไม่ผ่าน):** {fail_str}")

        st.markdown("---")
        st.subheader("👤 Operator Info")
        m1, m2, m3 = st.columns(3)
        m1.text_input("Name", data1["operator_name"], disabled=True)
        m2.text_input("Company", data1["company"], disabled=True)
        m3.text_input("Site", data1["site"], disabled=True)
        st.markdown("<br>", unsafe_allow_html=True)
        col_notes, col_recipe = st.columns(2)
        with col_notes: st.text_area("💬 Notes for the current file", data1["operator_comment"], height=150)
        with col_recipe: st.text_area("⚙ Recipe", data1["process_settings"], height=150)

        st.markdown("---")
        col_probes, col_img = st.columns(2)
        with col_probes:
            st.subheader("📍 Probe Locations")
            if data1["probe_locations"]:
                if f_variant == "NB1 (RAD)":
                    desired_order = ["PB#1", "PB#2", "PB#3", "PB#8", "PB#4", "PB#5", "PB#6", "PB#7"]
                    sorted_probes = sorted(data1["probe_locations"].items(), key=lambda x: desired_order.index(x[0]) if x[0] in desired_order else 99)
                else:
                    sorted_probes = sorted(data1["probe_locations"].items(), key=lambda x: int(x[0].replace("PB#", "")) if x[0].replace("PB#", "").isdigit() else 99)
                st.dataframe(pd.DataFrame([{"Channel": k, "Attached Location": v} for k, v in sorted_probes]), use_container_width=True, hide_index=True)
            else: st.info("No explicit probe location mapping found.")
        with col_img:
            if data1["embedded_img"]:
                st.subheader("🖼️ PAQ Image")
                st.image(data1["embedded_img"], use_container_width=True)

        st.markdown("---")
        st.subheader("🔥 Zone Peak Temperatures")
        zone_max_records = []
        for z in zones:
            z_df = df_m1[(df_m1["Distance_Meters"] >= z["start"]) & (df_m1["Distance_Meters"] < round(z["start"] + z["length"], 2))]
            r = {"Group": z["group"], "Zone #": z["num"], "Zone Name": z["name"], "Start (m)": z["start"], "End (m)": round(z["start"] + z["length"], 2)}
            if not z_df.empty and probe_cols:
                max_s = z_df[probe_cols].max()
                for col in probe_cols: r[col] = "***" if col in invalid_cols else max_s[col]
                valid_max = [max_s[c] for c in probe_cols if c not in invalid_cols and pd.notna(max_s[c])]
                r["Zone Peak (°C)"] = max(valid_max) if valid_max else np.nan
                r["Hot Probe"] = max_s[[c for c in probe_cols if c not in invalid_cols]].idxmax() if valid_max else "-"
            else:
                for col in probe_cols: r[col] = "***" if col in invalid_cols else np.nan
                r["Zone Peak (°C)"], r["Hot Probe"] = np.nan, "-"
            zone_max_records.append(r)
        df_zone_summary = pd.DataFrame(zone_max_records)
        valid_cols_for_bg = [c for c in probe_cols if c not in invalid_cols]
        try: st.dataframe(df_zone_summary.style.background_gradient(cmap="OrRd", subset=valid_cols_for_bg + ["Zone Peak (°C)"]).format({col: "{:.2f}" for col in valid_cols_for_bg + ["Zone Peak (°C)"]}), use_container_width=True)
        except: st.dataframe(df_zone_summary, use_container_width=True)

        st.markdown("---")
        st.subheader("⏱️ Entry Alignment (60°C)")
        shift_rows = []
        for col, info in data1["probe_start_info"].items():
            if col in invalid_cols: shift_rows.append({"Probe": col, "Start Time (HH:MM:SS)": "***", "Start Sec": "***", "Lag Time vs First": "***", "Distance Shift": "***", "Status": "*** (Inactive)"})
            else: shift_rows.append({"Probe": col, "Start Time (HH:MM:SS)": info["Start_HHMMSS"], "Start Sec": f"{info['Start_Sec']}s", "Lag Time vs First": f"+{info['Offset_Sec']}s" if info['Offset_Sec'] > 0 else "0s (Lead)", "Distance Shift": f"+{info['Offset_Meters']:.2f} m" if info['Offset_Meters'] > 0 else "0.00 m (Lead)", "Status": "🏆 First (Lead)" if info["Is_First"] else f"+{info['Offset_Meters']:.2f} m lag"})
        st.dataframe(pd.DataFrame(shift_rows), use_container_width=True, hide_index=True)
        
        st.markdown("---")
        st.subheader("📈 Temperature Distribution Boxplot by Probe")
        fig_box = go.Figure()
        for idx, col in enumerate(probe_cols): 
            if col not in invalid_cols: fig_box.add_trace(go.Box(y=df_m1[col].dropna(), name=col, boxpoints='outliers', marker_color=PROBE_COLORS.get(col)))
        fig_box.update_layout(title="Temperature Distribution Across Probes", yaxis_title="Temperature (°C)", template="plotly_white", height=500)
        st.plotly_chart(fig_box, use_container_width=True)

        st.markdown("---")
        st.subheader("📊 Zone Temperature Statistics (All Probes Combined)")
        stats_list = []
        for z in zones:
            df_z = df_m1[(df_m1["Distance_Meters"] >= z["start"]) & (df_m1["Distance_Meters"] <= z["start"] + z["length"])]
            if not df_z.empty:
                z_vals = df_z[[c for c in probe_cols if c not in invalid_cols]].values.flatten()
                z_vals = z_vals[~np.isnan(z_vals)]
                if len(z_vals) > 0: stats_list.append({"Zone #": z["num"], "Zone Name": z["name"], "Group": z["group"], "Avg Temp (°C)": round(np.mean(z_vals), 2), "Std Dev (°C)": round(np.std(z_vals, ddof=1), 2), "Min Temp (°C)": round(np.min(z_vals), 2), "Max Temp (°C)": round(np.max(z_vals), 2), "Data Points": len(z_vals) })
        df_stats = pd.DataFrame(stats_list)
        if not df_stats.empty:
            try: st.dataframe(df_stats.style.apply(highlight_row_by_group, axis=1), use_container_width=True, hide_index=True)
            except: st.dataframe(df_stats, use_container_width=True, hide_index=True)

        st.markdown("---")
        show_indiv_chart = st.toggle("👁 Show / Hide Individually Aligned Chart", value=False)
        if show_indiv_chart:
            st.subheader("Individually Aligned Probe Chart (Own 60°C Entry)")
            fig2 = go.Figure()
            for col in probe_cols:
                if col in invalid_cols:
                    fig2.add_trace(go.Scatter(x=[np.nan], y=[np.nan], mode="lines", name=f"<span style='color:gray'>{col} (Inactive)</span>", hovertemplate=f"{col} (Inactive)<extra></extra>", line=dict(color=PROBE_COLORS.get(col))))
                    continue
                offset_m = data1["probe_start_info"][col]["Offset_Meters"]
                indiv_hover = np.stack((df_m1["Time_HHMMSS"], df_m1["Time_Seconds"], np.full(len(df_m1), offset_m)), axis=-1)
                disp_name = f"{col} (+{offset_m:.2f}m)" if offset_m > 0 else f"{col} (Lead)"
                fig2.add_trace(go.Scatter(x=df_m1[f"Distance_{col}"], y=df_m1[col], mode="lines", name=disp_name, customdata=indiv_hover, hovertemplate=f"{col}: %{{y:.1f}} °C<br>Indiv Dist: %{{x:.2f}} m<br>Time: %{{customdata[0]}}", line=dict(color=PROBE_COLORS.get(col))))
            for z in zones:
                z_color = GROUP_COLORS.get(z["group"], "rgba(200, 200, 200, 0.2)")
                fig2.add_vrect(x0=z["start"], x1=z["start"] + z["length"], fillcolor=z_color, layer="below", line_width=0.5, line_dash="dot", line_color="rgba(120, 120, 120, 0.4)", annotation_text=f"{z['num']}.{z['name']}", annotation_position="top left", annotation=dict(font_size=9, font_color="#a0aab2", textangle=-90))
            fig2.update_layout(title=f"INDIVIDUALLY ALIGNED PROFILES ({f_variant}): {data1['filename']}", xaxis=dict(title="Individual Probe Distance (Meters from Probe's 60°C Entry)", range=[-1, total_furnace_length + 2]), yaxis_title="Temperature (°C)", hovermode="x unified", template="plotly_white", height=550)
            st.plotly_chart(fig2, use_container_width=True)

        st.markdown("---")
        st.subheader("💾 Data Export & Download")
        row_data = {"File_Name": data1["filename"], "Furnace_Type": f_variant, "Operator_Name": data1["operator_name"], "Company": data1["company"], "Site": data1["site"], "Entrance_Time": data1["detected_start_hhmmss"], "Line_Speed_MPM": data1["line_speed_mpm"]}
        max_export_pb = max([int(c.replace("PB#", "")) for c in probe_cols] + [8])
        for pb in [f"PB{i}" for i in range(1, max_export_pb + 1)]:
            ch = f"PB#{pb.replace('PB','')}"
            if ch in probe_cols:
                row_data[f"{pb}_Location"] = data1["probe_locations"].get(ch, "Unlabeled")
                if ch in invalid_cols:
                    row_data[f"{pb}_Start_Time"] = "***"
                    row_data[f"{pb}_Lag_Sec"] = "***"
                else:
                    row_data[f"{pb}_Start_Time"] = data1["probe_start_info"].get(ch, {}).get("Start_HHMMSS", "00:00:00")
                    row_data[f"{pb}_Lag_Sec"] = data1["probe_start_info"].get(ch, {}).get("Offset_Sec", 0)
            else:
                row_data[f"{pb}_Location"] = "No Data"
                row_data[f"{pb}_Start_Time"] = "N/A"
                row_data[f"{pb}_Lag_Sec"] = ""
                
        df_single_row = pd.DataFrame([row_data])
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### 📊 1. Analysis Report")
            report_format = st.radio("เลือกชนิดไฟล์ (Select Format):", ["Excel (.xlsx)", "CSV (.csv)"], horizontal=True, key="radio_report")
            if report_format == "Excel (.xlsx)":
                buffer_report = io.BytesIO()
                with pd.ExcelWriter(buffer_report, engine='openpyxl') as writer:
                    df_single_row.to_excel(writer, sheet_name="Master_Record", index=False)
                    df_zone_summary.to_excel(writer, sheet_name="Zone_Peaks", index=False)
                    pd.DataFrame(matrix_rows).to_excel(writer, sheet_name="Inspection_Matrix", index=False)
                st.download_button(label="📥 Download Report (.xlsx)", data=buffer_report.getvalue(), file_name=f"{os.path.splitext(data1['filename'])[0]}_Report.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
            elif report_format == "CSV (.csv)":
                csv_data = pd.concat([df_single_row, pd.DataFrame(matrix_rows)], axis=0).to_csv(index=False).encode('utf-8')
                st.download_button(label="📥 Download Report (.csv)", data=csv_data, file_name=f"{os.path.splitext(data1['filename'])[0]}_Report.csv", mime="text/csv", use_container_width=True)
                
        with col2:
            st.markdown("#### 📈 2. Raw Profile Data")
            raw_format = st.radio("เลือกชนิดไฟล์ (Select Format):", ["CSV (.csv)", "Excel (.xlsx)"], horizontal=True, key="radio_raw")
            df_raw_export = df_m1.drop(columns=[c for c in df_m1.columns if "Distance_PB#" in c], errors='ignore')
            if raw_format == "Excel (.xlsx)":
                buffer_raw = io.BytesIO()
                with pd.ExcelWriter(buffer_raw, engine='openpyxl') as writer: df_raw_export.to_excel(writer, sheet_name="Raw_Profile_Data", index=False)
                st.download_button(label="📥 Download Raw Data (.xlsx)", data=buffer_raw.getvalue(), file_name=f"{os.path.splitext(data1['filename'])[0]}_RawData.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
            elif raw_format == "CSV (.csv)":
                csv_data = df_raw_export.to_csv(index=False).encode('utf-8')
                st.download_button(label="📥 Download Raw Data (.csv)", data=csv_data, file_name=f"{os.path.splitext(data1['filename'])[0]}_RawData.csv", mime="text/csv", use_container_width=True)

# ---------------------------------------------------------
# TAB 1: COMPARE FILES
# ---------------------------------------------------------
with tabs[1]:
    if not data1:
        st.markdown('<div class="custom-warning-box">⚠️ <b>กรุณาอัปโหลดไฟล์หลัก (.PAQ) ที่แถบด้านซ้ายมือก่อน!</b> โหมด Compare จำเป็นต้องใช้ข้อมูลจากไฟล์หลักเพื่อใช้เป็นจุดอ้างอิงในการเปรียบเทียบกราฟครับ</div>', unsafe_allow_html=True)
    else:
        st.subheader("⚖️ Compare Profiles Across Two Files")
        uploaded_file2 = st.file_uploader("📂 Upload 2nd .PAQ File to Compare", type=["paq"], key=f"paq2_{st.session_state.paq2_uploader_key}")
        
        if not uploaded_file2: 
            st.markdown('<div class="custom-info-box">👆 <b>กรุณาอัปโหลดไฟล์ที่ 2 (.paq) ที่ช่องด้านบนด้วย NB เดียวกัน เพื่อแสดงผลกราฟเปรียบเทียบครับ</b></div>', unsafe_allow_html=True)
        else:
            data2 = process_paq_file(uploaded_file2.getvalue(), uploaded_file2.name)
            if not data2: 
                st.error("❌ Failed to parse second `.paq` file.")
            elif re.sub(r'[^A-Za-z0-9]', '', data1["furnace_id"]) != re.sub(r'[^A-Za-z0-9]', '', data2["furnace_id"]):
                st.markdown(f'<div class="custom-warning-box">⚠️ <b>กรุณาอัปโหลดไฟล์เปรียบเทียบจากเตาเดียวกัน ({data1["furnace_id"]})!</b><br>คุณกำลังพยายามเปรียบเทียบข้ามเตา (ไฟล์หลัก: <b>{data1["furnace_id"]}</b> / ไฟล์ที่เลือก: <b>{data2["furnace_id"]}</b>)<br><i>*สามารถเปรียบเทียบต่างรุ่นหรือต่างผลิตภัณฑ์ได้ แต่ต้องมาจากกระบวนการเตาเดียวกัน (NB เดียวกัน) ครับ</i></div>', unsafe_allow_html=True)
                if st.button("🔄 รับทราบและเลือกไฟล์ใหม่ (Acknowledge & Select New File)"):
                    st.session_state.paq2_uploader_key += 1
                    st.rerun()
            else:
                df_m2, fig_comp = data2["df_master"], go.Figure()
                custom_hover1 = np.stack((df_m1["Time_HHMMSS"], df_m1["Time_Seconds"], df_m1["Distance_Meters"]), axis=-1)
                custom_hover2 = np.stack((df_m2["Time_HHMMSS"], df_m2["Time_Seconds"], df_m2["Distance_Meters"]), axis=-1)

                for z in zones:
                    z_color = GROUP_COLORS.get(z["group"], "rgba(200, 200, 200, 0.2)")
                    fig_comp.add_vrect(x0=z["start"], x1=z["start"] + z["length"], fillcolor=z_color, layer="below", line_width=0.5, line_dash="dot", line_color="rgba(120, 120, 120, 0.4)", annotation_text=f"{z['num']}.{z['name']}", annotation_position="top left", annotation=dict(font_size=9, font_color="#a0aab2", textangle=-90))
                
                fig_comp.add_hline(y=cfg["trigger_temp_brazing"], line_dash="dash", line_color="red", annotation_text=f"Brazing ({cfg['trigger_temp_brazing']}°C)", annotation_position="bottom right")
                
                for col in probe_cols:
                    if col in df_m1.columns: 
                        legend_name = f"<span style='color:gray'>F1: {col}</span>" if col in invalid_cols else f"F1: {col}"
                        fig_comp.add_trace(go.Scatter(x=df_m1["Distance_Meters"], y=df_m1[col], mode="lines", name=legend_name, customdata=custom_hover1, hovertemplate=f"F1 {col}: %{{y:.1f}} °C<br>Time: %{{customdata[0]}}<br>Dist: %{{x:.2f}} m", line=dict(color=PROBE_COLORS.get(col), width=1.5)))
                for col in data2["probe_cols"]:
                    if col in df_m2.columns: 
                        legend_name = f"<span style='color:gray'>F2: {col}</span>" if col in data2["invalid_cols"] else f"F2: {col}"
                        fig_comp.add_trace(go.Scatter(x=df_m2["Distance_Meters"], y=df_m2[col], mode="lines", name=legend_name, customdata=custom_hover2, hovertemplate=f"F2 {col}: %{{y:.1f}} °C<br>Time: %{{customdata[0]}}<br>Dist: %{{x:.2f}} m", line=dict(dash='dash', color=PROBE_COLORS.get(col), width=1.5)))
                
                d_max_view = total_furnace_length + 1.0
                d_min_comp = min(df_m1["Distance_Meters"].min(), df_m2["Distance_Meters"].min())
                d_max_actual = max(df_m1["Distance_Meters"].max(), df_m2["Distance_Meters"].max())
                d_max_comp = min(d_max_actual, d_max_view)

                fig_comp.update_layout(title=f"COMPARISON: {data1['filename']} vs {data2['filename']}", yaxis=dict(title="Temperature (°C)"), hovermode="x unified", template="plotly_white", height=600, margin=dict(b=80), xaxis=dict(title="Distance (Meters)", range=[d_min_comp, d_max_comp]))
                st.plotly_chart(fig_comp, use_container_width=True)
                
                st.markdown("---")
                st.markdown("##### 📥 Export Compare Data")
                df_comp1 = df_m1[['Distance_Meters'] + [c for c in probe_cols if c in df_m1.columns]].copy()
                df_comp2 = df_m2[['Distance_Meters'] + [c for c in data2["probe_cols"] if c in df_m2.columns]].copy()
                df_comp1.columns = ['Distance_Meters'] + [f"F1_{c}" for c in df_comp1.columns if c != 'Distance_Meters']
                df_comp2.columns = ['Distance_Meters'] + [f"F2_{c}" for c in df_comp2.columns if c != 'Distance_Meters']
                
                df_comp1['Merge_Dist'], df_comp2['Merge_Dist'] = df_comp1['Distance_Meters'].round(2), df_comp2['Distance_Meters'].round(2)
                df_merged = pd.merge(df_comp1, df_comp2, on='Merge_Dist', how='outer').sort_values('Merge_Dist').drop(columns=['Merge_Dist'])
                st.download_button(label="📊 Download Compared Data (.xlsx)", data=to_excel_bytes(df_merged), file_name="Compared_Profile_Data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, type="primary")

# ---------------------------------------------------------
# TAB 2: COMBINE RECORDER DATA
# ---------------------------------------------------------
with tabs[2]:
    st.markdown("### 🔗 Recorder Data (Standalone / Combine)")
    display_mode = st.radio("รูปแบบการแสดงผล (Display Mode):", ("แสดงกราฟ Recorder อย่างเดียว (Standalone Mode)", "ผสานกราฟ Datapaq และ Recorder (Combine Mode)"), horizontal=True)
    st.markdown("---")

    if display_mode == "แสดงกราฟ Recorder อย่างเดียว (Standalone Mode)":
        col_title, col_clear = st.columns([4, 1])
        with col_title: st.markdown("### 📁 Upload Recorder Data (Standalone Mode)")
        with col_clear:
            st.markdown("<div style='margin-top: 5px;'></div>", unsafe_allow_html=True)
            if st.button("🗑️ Clear Data", key="clear_recorder_btn", use_container_width=True):
                st.session_state.recorder_uploader_key += 1
                st.rerun()
            
        st.markdown('<div class="custom-info-box">💡 <b>โหมดนี้จะแสดงผลกราฟของ Recorder เดี่ยวๆ</b> โดยสามารถดูข้อมูลของเตาใดก็ได้ ไม่ต้องอ้างอิงกับไฟล์ Datapaq หลัก</div>', unsafe_allow_html=True)
        rec_file_type = st.radio("เลือกประเภทเตาและไฟล์ (Select Furnace & File Type):", ("NB1 / NB2 Furnace Recorder (.DAD)", "NB3 Furnace Recorder (.CSV)", "NB1 Debinder Furnace Recorder (.CSV)"), horizontal=True)
        
        uploaded_rec_files = None
        if rec_file_type == "NB1 / NB2 Furnace Recorder (.DAD)":
            uploaded_rec_files = st.file_uploader("Drop .DAD here", type=["dad"], accept_multiple_files=True, key=f"std_dad_{st.session_state.recorder_uploader_key}", label_visibility="collapsed")
            if uploaded_rec_files:
                files_data = [(f.name, f.read()) for f in uploaded_rec_files]
                machine_type, active_channels = check_machine_type([f[0] for f in files_data])
                if machine_type == 'MIXED': st.error('🚨 ตรวจพบการอัปโหลดไฟล์จากทั้งเครื่อง NB1 และ NB2 ปะปนกัน! กรุณากดปุ่ม "Clear Data" และอัปโหลดไฟล์แยกเครื่องกันครับ')
                else:
                    value_mode = st.selectbox('เลือกประเภทของค่าที่ต้องการวิเคราะห์:', options=['MIN', 'AVG (เฉลี่ย)', 'MAX'], index=2)
                    mode_key = {'MIN': '_min', 'AVG (เฉลี่ย)': '_avg', 'MAX': '_max'}[value_mode]
                    data = process_dad_files(tuple((n,d) for n,d in files_data), mode_key, tuple(active_channels))
                    if not data: st.error('🚨 ไม่พบข้อมูลในไฟล์ที่อัปโหลด')
                    else:
                        st.success(f"✓ โหลดข้อมูล {len(data)} แถว สำเร็จ (ช่วงเวลา: {data[0]['ts']} ถึง {data[-1]['ts']})")
                        tb_y_range = [540, 650] if machine_type == 'NB1' else [400, 650]
                        top_chs = [ch for ch in active_channels if ch[0] in ['CH001','CH002','CH003','CH004','CH005','CH006','CH007']]
                        bot_chs = [ch for ch in active_channels if ch[0] in ['CH008','CH009','CH010','CH011','CH012','CH013','CH014']]
                        dry_chs = [ch for ch in active_channels if ch[0] in ['CH016','CH017']]
                        dry_y_range = [150, 350] if machine_type == 'NB1' else [150, 400]
                        split_charts = st.toggle("📊 แยกกราฟ Top / Bottom / Dryer เป็นรายโซนย่อย (Split Zone Charts)", key="split_std_dad")
                        
                        if split_charts:
                            st.markdown("#### Top Zones")
                            for i, ch in enumerate(top_chs):
                                std_min, std_max = RECORDER_STANDARDS.get(machine_type, {}).get("Top", [None]*7)[i] if i < 7 else (None, None)
                                fig_top = render_single_chart(data, [ch], [COLORS_TOP[i % len(COLORS_TOP)]], f'{ch[1]} ({machine_type})', tb_y_range, '°C', std_min=std_min, std_max=std_max)
                                if fig_top: st.plotly_chart(fig_top, use_container_width=True)
                            st.markdown("#### Bottom Zones")
                            for i, ch in enumerate(bot_chs):
                                std_min, std_max = RECORDER_STANDARDS.get(machine_type, {}).get("Bottom", [None]*7)[i] if i < 7 else (None, None)
                                fig_bot = render_single_chart(data, [ch], [COLORS_BOT[i % len(COLORS_BOT)]], f'{ch[1]} ({machine_type})', tb_y_range, '°C', std_min=std_min, std_max=std_max)
                                if fig_bot: st.plotly_chart(fig_bot, use_container_width=True)
                            st.markdown("#### Dryer Zones")
                            for i, ch in enumerate(dry_chs):
                                std_min, std_max = RECORDER_STANDARDS.get(machine_type, {}).get("Dryer", [None]*3)[i] if i < 3 else (None, None)
                                fig_dry = render_single_chart(data, [ch], {ch[0]: COLORS_DRY.get(ch[0], '#FFA500')}, f'{ch[1]} ({machine_type})', dry_y_range, '°C', std_min=std_min, std_max=std_max)
                                if fig_dry: st.plotly_chart(fig_dry, use_container_width=True)
                        else:
                            fig_top = render_single_chart(data, top_chs, COLORS_TOP, f'Top Zones Temperature ({machine_type})', tb_y_range, '°C')
                            if fig_top: st.plotly_chart(fig_top, use_container_width=True)
                            fig_bot = render_single_chart(data, bot_chs, COLORS_BOT, f'Bottom Zones Temperature ({machine_type})', tb_y_range, '°C')
                            if fig_bot: st.plotly_chart(fig_bot, use_container_width=True)
                            fig_dry = render_single_chart(data, dry_chs, COLORS_DRY, f'Dryer Zones Temperature ({machine_type})', dry_y_range, '°C')
                            if fig_dry: st.plotly_chart(fig_dry, use_container_width=True)
                        
                        if machine_type == 'NB2':
                            fig_o2 = render_single_chart(data, [ch for ch in active_channels if ch[0] in ['CH015', 'CH018']], COLORS_O2_NB2, 'O2 Concentration Level', [0, 150], 'ppm', hline=100)
                            if fig_o2: st.plotly_chart(fig_o2, use_container_width=True)
                        else:
                            fig_o2_n2 = render_dual_axis_chart(data, [ch for ch in active_channels if ch[0] in ['CH015', 'CH019']], [ch for ch in active_channels if ch[0] == 'CH018'], COLORS_O2_NB1, COLORS_N2, 'O2 Concentration & N2 Flow Rate', [0, 150], 'O2 (ppm)', '', hline_left=100, y2_range=[0, 5000])
                            if fig_o2_n2: st.plotly_chart(fig_o2_n2, use_container_width=True)
                            fig_dew = render_single_chart(data, [ch for ch in active_channels if ch[0] == 'CH020'], COLORS_DEW, 'Dew Point', [-100, 10], 'Cdp', hline=-40)
                            if fig_dew: 
                                fig_dew.update_layout(yaxis=dict(range=[-100, 10], autorange=False, title_text='Cdp'))
                                st.plotly_chart(fig_dew, use_container_width=True)
                        
                        st.markdown("---")
                        st.download_button(label="📊 Download Recorder Data (.xlsx)", data=to_excel_bytes(pd.DataFrame(data)), file_name="Recorder_Data_Standalone.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, type="primary")

        elif rec_file_type == "NB3 Furnace Recorder (.CSV)":
            uploaded_rec_files = st.file_uploader("Drop .CSV here", type=["csv"], accept_multiple_files=True, key=f"std_nb3_csv_{st.session_state.recorder_uploader_key}", label_visibility="collapsed")
            if uploaded_rec_files:
                df_nb3 = process_nb3_files(uploaded_rec_files)
                if not df_nb3.empty:
                    start_time_nb3 = extract_csv_start_time(df_nb3, ["Top Zone #1", "Top Zone #2", "Bottom Zone #1", "Bottom Zone #2"])
                    if start_time_nb3 is not None: st.success(f"✓ โหลดข้อมูล {len(df_nb3)} แถว สำเร็จ (ช่วงเวลา: {df_nb3['DateTime'].min()} ถึง {df_nb3['DateTime'].max()})\n\n**Process Started at:** {start_time_nb3}")
                    else: st.success(f"✓ โหลดข้อมูล {len(df_nb3)} แถว สำเร็จ (ช่วงเวลา: {df_nb3['DateTime'].min()} ถึง {df_nb3['DateTime'].max()})")
                    
                    split_charts = st.toggle("📊 แยกกราฟ Top / Bottom / Dryer เป็นรายโซนย่อย", key="split_std_nb3_csv")
                    top_colors, bottom_colors, dry_colors = ["#FF0000", "#008000", "#0000FF", "#8A2BE2", "#A52A2A", "#FFA500", "#9ACD32"], ["#00BFFF", "#FF1493", "#808080", "#00FF00", "#008000", "#0000FF", "#8A2BE2"], ["#FFA500", "#9ACD32", "#008B8B"]
                    dryoff_names = ["DRYOFF1", "DRYOFF2", "DRYOFF3"]

                    if split_charts:
                        st.markdown("##### 1) Top Zones")
                        for i in range(1, 8):
                            if f"Top Zone #{i}" in df_nb3.columns:
                                std_min, std_max = RECORDER_STANDARDS["NB3"]["Top"][i-1] if i-1 < len(RECORDER_STANDARDS["NB3"]["Top"]) else (None, None)
                                fig = go.Figure(go.Scatter(x=df_nb3["DateTime"], y=df_nb3[f"Top Zone #{i}"], name=f"Top Zone #{i}", mode="lines", line=dict(color=top_colors[i-1], width=2)))
                                apply_industrial_style(fig, "Temperature (°C)", std_min=std_min, std_max=std_max, ts=df_nb3["DateTime"])
                                st.plotly_chart(fig, use_container_width=True)
                        st.markdown("##### 2) Bottom Zones")
                        for i in range(1, 8):
                            if f"Bottom Zone #{i}" in df_nb3.columns:
                                std_min, std_max = RECORDER_STANDARDS["NB3"]["Bottom"][i-1] if i-1 < len(RECORDER_STANDARDS["NB3"]["Bottom"]) else (None, None)
                                fig = go.Figure(go.Scatter(x=df_nb3["DateTime"], y=df_nb3[f"Bottom Zone #{i}"], name=f"Bottom Zone #{i}", mode="lines", line=dict(color=bottom_colors[i-1], width=2)))
                                apply_industrial_style(fig, "Temperature (°C)", std_min=std_min, std_max=std_max, ts=df_nb3["DateTime"])
                                st.plotly_chart(fig, use_container_width=True)
                        st.markdown("##### 3) DRYOFF")
                        for i in range(1, 4):
                            if dryoff_names[i-1] in df_nb3.columns:
                                std_min, std_max = RECORDER_STANDARDS["NB3"]["Dryer"][i-1] if i-1 < len(RECORDER_STANDARDS["NB3"]["Dryer"]) else (None, None)
                                fig = go.Figure(go.Scatter(x=df_nb3["DateTime"], y=df_nb3[dryoff_names[i-1]], name=dryoff_names[i-1], mode="lines", line=dict(color=dry_colors[i-1], width=2)))
                                apply_industrial_style(fig, "Temperature (°C)", std_min=std_min, std_max=std_max, ts=df_nb3["DateTime"])
                                st.plotly_chart(fig, use_container_width=True)
                    else:
                        fig1 = go.Figure()
                        for i in range(1, 8):
                            if f"Top Zone #{i}" in df_nb3.columns: fig1.add_trace(go.Scatter(x=df_nb3["DateTime"], y=df_nb3[f"Top Zone #{i}"], name=f"Top Zone #{i}", mode="lines", line=dict(color=top_colors[i-1], width=2)))
                        apply_industrial_style(fig1, "Temperature (°C)")
                        st.plotly_chart(fig1, use_container_width=True)

                        fig2 = go.Figure()
                        for i in range(1, 8):
                            if f"Bottom Zone #{i}" in df_nb3.columns: fig2.add_trace(go.Scatter(x=df_nb3["DateTime"], y=df_nb3[f"Bottom Zone #{i}"], name=f"Bottom Zone #{i}", mode="lines", line=dict(color=bottom_colors[i-1], width=2)))
                        apply_industrial_style(fig2, "Temperature (°C)")
                        st.plotly_chart(fig2, use_container_width=True)

                        fig3 = go.Figure()
                        for i in range(1, 4):
                            if dryoff_names[i-1] in df_nb3.columns: fig3.add_trace(go.Scatter(x=df_nb3["DateTime"], y=df_nb3[dryoff_names[i-1]], name=dryoff_names[i-1], mode="lines", line=dict(color=dry_colors[i-1], width=2)))
                        apply_industrial_style(fig3, "Temperature (°C)")
                        st.plotly_chart(fig3, use_container_width=True)

                    st.markdown("##### 4) Oxygen EXIT/ENTRANCE & N2 Flow")
                    fig4 = make_subplots(specs=[[{"secondary_y": True}]])
                    if "Oxygen EXIT" in df_nb3.columns: fig4.add_trace(go.Scatter(x=df_nb3["DateTime"], y=df_nb3["Oxygen EXIT"], name="Oxygen EXIT", mode="lines", line=dict(color="#FF00FF", width=2)), secondary_y=False)
                    if "Oxygen ENTRANCE" in df_nb3.columns: fig4.add_trace(go.Scatter(x=df_nb3["DateTime"], y=df_nb3["Oxygen ENTRANCE"], name="Oxygen ENTRANCE", mode="lines", line=dict(color="#A52A2A", width=2)), secondary_y=False)
                    if "N2 Exit" in df_nb3.columns: fig4.add_trace(go.Scatter(x=df_nb3["DateTime"], y=df_nb3["N2 Exit"], name="N2 Exit", mode="lines", line=dict(color="#1f77b4", width=2, dash="dash")), secondary_y=True)
                    if "N2 Entrance" in df_nb3.columns: fig4.add_trace(go.Scatter(x=df_nb3["DateTime"], y=df_nb3["N2 Entrance"], name="N2 Entrance", mode="lines", line=dict(color="#2ca02c", width=2, dash="dash")), secondary_y=True)
                    apply_industrial_style(fig4, "Oxygen Level (ppm)", is_dual_axis=True)
                    fig4.update_layout(yaxis=dict(title=dict(text="Oxygen Level (ppm) [0-200]"), range=[0, 200], showgrid=True), yaxis2=dict(title=dict(text="N2 Flow Rate [0-1000]"), showgrid=False, overlaying="y", side="right", range=[0, 1000]))
                    st.plotly_chart(fig4, use_container_width=True)

                    st.markdown("##### 5) COOL WATER TEMP")
                    fig5 = go.Figure()
                    if "COOL WATER TEMP" in df_nb3.columns: fig5.add_trace(go.Scatter(x=df_nb3["DateTime"], y=df_nb3["COOL WATER TEMP"], name="COOL WATER TEMP", mode="lines", line=dict(color="#008B8B", width=2)))
                    apply_industrial_style(fig5, "Cool Water Temp (°C)", y_range=[-150, 500])
                    st.plotly_chart(fig5, use_container_width=True)
                    st.markdown("---")
                    st.download_button(label="📊 Download Recorder Data (.xlsx)", data=to_excel_bytes(df_nb3), file_name="NB3_Recorder_Data_Standalone.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, type="primary")

        elif rec_file_type == "NB1 Debinder Furnace Recorder (.CSV)":
            uploaded_rec_files = st.file_uploader("Drop .CSV here", type=["csv"], accept_multiple_files=True, key=f"std_nb1_csv_{st.session_state.recorder_uploader_key}", label_visibility="collapsed")
            if uploaded_rec_files:
                df_deb = process_debinder_files(uploaded_rec_files)
                if not df_deb.empty:
                    start_time_deb = extract_csv_start_time(df_deb, ["Zone #1", "Zone #2"])
                    if start_time_deb is not None: st.success(f"✓ โหลดข้อมูล {len(df_deb)} แถว สำเร็จ (ช่วงเวลา: {df_deb['DateTime'].min()} ถึง {df_deb['DateTime'].max()})\n\n**Process Started at:** {start_time_deb}")
                    else: st.success(f"✓ โหลดข้อมูล {len(df_deb)} แถว สำเร็จ (ช่วงเวลา: {df_deb['DateTime'].min()} ถึง {df_deb['DateTime'].max()})")
                    split_charts = st.toggle("📊 แยกกราฟเป็นรายโซนย่อย", key="split_std_deb_csv")
                    zone_colors = ["#FF3333", "#1E90FF", "#2ED573", "#FF9F1A"]
                    
                    if split_charts:
                        st.markdown("##### Debinder Zones")
                        for i in range(1, 5):
                            std_min, std_max = RECORDER_STANDARDS["NB1"]["Debinder"][i-1] if i-1 < len(RECORDER_STANDARDS["NB1"]["Debinder"]) else (None, None)
                            fig = go.Figure(go.Scatter(x=df_deb["DateTime"], y=df_deb[f"Zone #{i}"], name=f"Zone #{i} (Max)", mode="lines", line=dict(color=zone_colors[i-1], width=2)))
                            apply_industrial_style(fig, "Temperature (°C)", y_range=[0, 400], std_min=std_min, std_max=std_max, ts=df_deb["DateTime"])
                            st.plotly_chart(fig, use_container_width=True)
                        st.markdown("##### Combustion Air Temp")
                        fig_comb = go.Figure(go.Scatter(x=df_deb["DateTime"], y=df_deb["Combustion Air Temp"], name="Comb Air (Max)", mode="lines", line=dict(color="#00E5FF", width=2, dash="dash")))
                        apply_industrial_style(fig_comb, "Comb Air (°C)", y_range=[0, 150])
                        st.plotly_chart(fig_comb, use_container_width=True)
                    else:
                        fig = make_subplots(specs=[[{"secondary_y": True}]])
                        for i in range(1, 5): fig.add_trace(go.Scatter(x=df_deb["DateTime"], y=df_deb[f"Zone #{i}"], name=f"Zone #{i} (Max)", mode="lines", line=dict(color=zone_colors[i-1], width=2)), secondary_y=False)
                        fig.add_trace(go.Scatter(x=df_deb["DateTime"], y=df_deb["Combustion Air Temp"], name="Comb Air (Max)", mode="lines", line=dict(color="#00E5FF", width=2, dash="dash")), secondary_y=True)
                        fig.update_layout(hovermode="x unified", height=450, margin=dict(l=60, r=180, t=30, b=40), yaxis=dict(range=[0, 400], title="Temperature (°C)"), yaxis2=dict(title="Comb Air (°C)", overlaying="y", side="right", range=[0, 150]))
                        st.plotly_chart(fig, use_container_width=True)
                    
                    st.markdown("---")
                    st.download_button(label="📊 Download Recorder Data (.xlsx)", data=to_excel_bytes(df_deb), file_name="NB1_Debinder_Data_Standalone.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, type="primary")

    # ==========================================
    # COMBINE MODE
    # ==========================================
    else:
        if not data1:
            st.markdown("### 📁 Upload Recorder Data (Combine Mode)")
            st.markdown('<div class="custom-warning-box">⚠️ <b>กรุณาอัปโหลดไฟล์หลัก (.PAQ) ที่แถบด้านซ้ายมือก่อน!</b> โหมด Combine จำเป็นต้องใช้ข้อมูลเวลาการเข้าเตาจากไฟล์ Datapaq เพื่อใช้เป็นจุดอ้างอิงในการผสานกราฟครับ</div>', unsafe_allow_html=True)
        else:
            furnace_id = data1["furnace_id"]
            st.markdown(f'<div class="custom-info-box">📌 <b>ข้อแนะนำ:</b> เตาหลักของคุณคือ <b>{furnace_id}</b> ระบบจะอนุญาตให้อัปโหลดเฉพาะไฟล์ของเตา <b>{furnace_id}</b> เท่านั้น</div>', unsafe_allow_html=True)
            
            col_date, col_time, col_furnace = st.columns(3)
            with col_date: 
                try: default_date_obj = data1["extracted_date"]
                except: default_date_obj = pd.Timestamp.now().date()
                edited_start_date = st.date_input("PAQ Run Date", value=default_date_obj)
            with col_time: 
                try: actual_start_time = data1["extracted_time"]
                except: actual_start_time = "00:00:00"
                edited_start_time = st.text_input("PAQ Collection Started", value=actual_start_time, help="เช่น 14:00:11 หรือ 02:22:55 PM")
            with col_furnace: st.text_input("Furnace", value=furnace_id, disabled=True)

            try:
                parsed_time = pd.to_datetime(edited_start_time).time()
                paq_start_dt = datetime.combine(edited_start_date, parsed_time)
            except:
                try:
                    time_parts = edited_start_time.replace('.', ':').split(':')
                    hh = int(time_parts[0]) if len(time_parts) > 0 else 0
                    mm = int(time_parts[1]) if len(time_parts) > 1 else 0
                    ss = int(time_parts[2]) if len(time_parts) > 2 else 0
                    paq_start_dt = datetime.combine(edited_start_date, time(hh, mm, ss))
                except: paq_start_dt = datetime.combine(edited_start_date, time(0, 0, 0))

            df_paq = data1["df_master"].copy()
            df_paq["Sync_DateTime"] = paq_start_dt + pd.to_timedelta(df_paq["Time_Seconds"] - data1['detected_start_sec'], unit="s")
            zones, total_furnace_length = data1["cfg"]["zones"], data1["cfg"]["zones"][-1]["start"] + data1["cfg"]["zones"][-1]["length"] if data1["cfg"]["zones"] else 0
            furnace_duration_secs = (total_furnace_length / data1['line_speed_mpm']) * 60 if data1.get('line_speed_mpm') else 3600
            zoom_x_range = [paq_start_dt - timedelta(minutes=5), paq_start_dt + timedelta(seconds=furnace_duration_secs + 300)]

            st.markdown("---")
            col_up_title, col_up_clear = st.columns([4, 1])
            with col_up_title: st.markdown(f"#### 📁 Upload Recorder Data for {furnace_id}")
            with col_up_clear:
                st.markdown("<div style='margin-top: 5px;'></div>", unsafe_allow_html=True)
                if st.button("🗑️ Clear Data", key="clear_combine_btn", use_container_width=True):
                    st.session_state.recorder_uploader_key += 1
                    st.rerun()
            
            rec_dad_files, rec_csv_files = None, None
            if furnace_id == "NB1":
                col_up1, col_up2 = st.columns(2)
                with col_up1: 
                    rec_dad_files = st.file_uploader(f"Upload {furnace_id} Recorder (.DAD) (Max:6)", type=["dad"], accept_multiple_files=True, key=f"cmb_dad_nb1_{st.session_state.recorder_uploader_key}")
                    if rec_dad_files and len(rec_dad_files) > 6: rec_dad_files = rec_dad_files[:6]
                with col_up2: 
                    rec_csv_files = st.file_uploader(f"Upload {furnace_id} Debinder (.CSV) (Max:2)", type=["csv"], accept_multiple_files=True, key=f"cmb_csv_nb1_{st.session_state.recorder_uploader_key}")
                    if rec_csv_files and len(rec_csv_files) > 2: rec_csv_files = rec_csv_files[:2]
            elif furnace_id == "NB2":
                rec_dad_files = st.file_uploader(f"Upload {furnace_id} Recorder (.DAD) (Max:6)", type=["dad"], accept_multiple_files=True, key=f"cmb_dad_nb2_{st.session_state.recorder_uploader_key}")
                if rec_dad_files and len(rec_dad_files) > 6: rec_dad_files = rec_dad_files[:6]
            elif furnace_id == "NB3":
                rec_csv_files = st.file_uploader(f"Upload {furnace_id} Furnace (.CSV) (Max:6)", type=["csv"], accept_multiple_files=True, key=f"cmb_csv_nb3_{st.session_state.recorder_uploader_key}")
                if rec_csv_files and len(rec_csv_files) > 6: rec_csv_files = rec_csv_files[:6]
                
            if rec_dad_files or rec_csv_files:
                st.markdown("#### 🔍 ตั้งค่าการแสดงผลกราฟ (View & Zoom Options)")
                zoom_mode = st.radio("เลือกรูปแบบการซูม (Zoom Mode):", ["แสดงกราฟเต็ม (Full Range)", "ซูมอัตโนมัติทุกกราฟ (Auto-Zoom All)"], horizontal=True)

            # Combine: NB1 & NB2 (.DAD)
            if rec_dad_files:
                files_data = [(f.name, f.read()) for f in rec_dad_files]
                machine_type, active_channels = check_machine_type([f[0] for f in files_data])
                if machine_type != furnace_id and machine_type != 'MIXED':
                    st.error(f"❌ **ไฟล์ไม่ถูกต้อง!** คุณกำลังวิเคราะห์เตา **{furnace_id}** แต่ไฟล์ .DAD ที่อัปโหลดเป็นของเครื่อง **{machine_type}**"); st.stop()
                elif machine_type == 'MIXED':
                    st.error('🚨 ตรวจพบการอัปโหลดไฟล์จากทั้งเครื่อง NB1 และ NB2 ปะปนกัน!'); st.stop()
                    
                data = process_dad_files(tuple((n,d) for n,d in files_data), '_max', tuple(active_channels))
                if data:
                    st.success("✅ Recorder files uploaded successfully! Generating Combined Overlay Charts...")
                    fixed_y_range, charts_to_render = [0, 650], []
                    top_chs = [ch for ch in active_channels if ch[0] in ['CH001','CH002','CH003','CH004','CH005','CH006','CH007']]
                    bot_chs = [ch for ch in active_channels if ch[0] in ['CH008','CH009','CH010','CH011','CH012','CH013','CH014']]
                    dry_chs = [ch for ch in active_channels if ch[0] in ['CH016','CH017']]
                    split_charts = st.toggle("📊 แยกกราฟ Top / Bottom / Dryer เป็นรายโซนย่อย", key="split_cmb_dad")

                    if split_charts:
                        for i, ch in enumerate(top_chs):
                            std_min, std_max = RECORDER_STANDARDS.get(machine_type, {}).get("Top", [None]*7)[i] if i < 7 else (None, None)
                            fig_top = render_single_chart(data, [ch], [COLORS_TOP[i % len(COLORS_TOP)]], f'Top Zone: {ch[1]} ({machine_type})', fixed_y_range, '°C', std_min=std_min, std_max=std_max)
                            add_paq_overlay(fig_top, df_paq, probe_cols, invalid_cols); add_zone_backgrounds(fig_top, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                            charts_to_render.append({"title": f"Top Zone: {ch[1]}", "fig": fig_top})
                        for i, ch in enumerate(bot_chs):
                            std_min, std_max = RECORDER_STANDARDS.get(machine_type, {}).get("Bottom", [None]*7)[i] if i < 7 else (None, None)
                            fig_bot = render_single_chart(data, [ch], [COLORS_BOT[i % len(COLORS_BOT)]], f'Bottom Zone: {ch[1]} ({machine_type})', fixed_y_range, '°C', std_min=std_min, std_max=std_max)
                            add_paq_overlay(fig_bot, df_paq, probe_cols, invalid_cols); add_zone_backgrounds(fig_bot, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                            charts_to_render.append({"title": f"Bottom Zone: {ch[1]}", "fig": fig_bot})
                        for i, ch in enumerate(dry_chs):
                            std_min, std_max = RECORDER_STANDARDS.get(machine_type, {}).get("Dryer", [None]*3)[i] if i < 3 else (None, None)
                            fig_dry = render_single_chart(data, [ch], {ch[0]: COLORS_DRY.get(ch[0], '#FFA500')}, f'Dryer Zone: {ch[1]} ({machine_type})', fixed_y_range, '°C', std_min=std_min, std_max=std_max)
                            add_paq_overlay(fig_dry, df_paq, probe_cols, invalid_cols); add_zone_backgrounds(fig_dry, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                            charts_to_render.append({"title": f"Dryer Zone: {ch[1]}", "fig": fig_dry})
                    else:
                        fig_top = render_single_chart(data, top_chs, COLORS_TOP, f'Top Zones ({machine_type})', fixed_y_range, '°C')
                        add_paq_overlay(fig_top, df_paq, probe_cols, invalid_cols); add_zone_backgrounds(fig_top, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                        charts_to_render.append({"title": "1) Top Zones", "fig": fig_top})
                        fig_bot = render_single_chart(data, bot_chs, COLORS_BOT, f'Bottom Zones ({machine_type})', fixed_y_range, '°C')
                        add_paq_overlay(fig_bot, df_paq, probe_cols, invalid_cols); add_zone_backgrounds(fig_bot, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                        charts_to_render.append({"title": "2) Bottom Zones", "fig": fig_bot})
                        fig_dry = render_single_chart(data, dry_chs, COLORS_DRY, f'Dryer Zones ({machine_type})', fixed_y_range, '°C')
                        add_paq_overlay(fig_dry, df_paq, probe_cols, invalid_cols); add_zone_backgrounds(fig_dry, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                        charts_to_render.append({"title": "3) Dryer Zones", "fig": fig_dry})
                    
                    if machine_type == 'NB2':
                        fig_o2 = render_single_chart(data, [ch for ch in active_channels if ch[0] in ['CH015', 'CH018']], COLORS_O2_NB2, 'O2 Concentration Level / PAQ (°C)', fixed_y_range, 'ppm', hline=100)
                        if fig_o2: 
                            add_paq_overlay(fig_o2, df_paq, probe_cols, invalid_cols); add_zone_backgrounds(fig_o2, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                            charts_to_render.append({"title": "4) O2 Concentration", "fig": fig_o2})
                    else:
                        fig_o2_n2 = render_dual_axis_chart(data, [ch for ch in active_channels if ch[0] in ['CH015', 'CH019']], [ch for ch in active_channels if ch[0] == 'CH018'], COLORS_O2_NB1, COLORS_N2, 'O2 Concentration & N2 Flow Rate', fixed_y_range, 'O2 (ppm) / PAQ (°C)', '', hline_left=100, y2_range=[0, 5000])
                        if fig_o2_n2: 
                            add_paq_overlay(fig_o2_n2, df_paq, probe_cols, invalid_cols, is_dual_axis=True); add_zone_backgrounds(fig_o2_n2, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                            charts_to_render.append({"title": "4) O2 & N2 Flow", "fig": fig_o2_n2})
                    
                    fig_dew = render_single_chart(data, [ch for ch in active_channels if ch[0] == 'CH020'], COLORS_DEW, 'Dew Point / PAQ (°C)', [-100, 650], 'Cdp', hline=-40)
                    if fig_dew: 
                        add_paq_overlay(fig_dew, df_paq, probe_cols, invalid_cols); add_zone_backgrounds(fig_dew, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                        charts_to_render.append({"title": "5) Dew Point", "fig": fig_dew})
                        
                    render_combined_charts_vertically(charts_to_render, zoom_mode, zoom_x_range, "dad")
                    
                    st.markdown("---")
                    df_rec = pd.DataFrame(data).rename(columns={'ts': 'Sync_DateTime'}) if 'ts' in pd.DataFrame(data).columns else pd.DataFrame(data)
                    df_merged = pd.merge(df_rec, df_paq[['Sync_DateTime'] + [c for c in probe_cols if c in df_paq.columns]], on='Sync_DateTime', how='outer').sort_values('Sync_DateTime')
                    st.download_button(label="📊 Download Combined Data (.xlsx)", data=to_excel_bytes(df_merged), file_name="Combined_Recorder_Datapaq.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, type="primary")

            # Combine: NB1 Debinder (.CSV)
            if rec_csv_files and furnace_id == "NB1":
                df_deb = process_debinder_files(rec_csv_files, expected_furnace="NB1")
                if not df_deb.empty:
                    charts_to_render, zone_colors = [], ["#FF3333", "#1E90FF", "#2ED573", "#FF9F1A"]
                    split_charts = st.toggle("📊 แยกกราฟเป็นรายโซนย่อย", key="split_cmb_deb_csv")
                    
                    if split_charts:
                        for i in range(1, 5):
                            std_min, std_max = RECORDER_STANDARDS["NB1"]["Debinder"][i-1] if i-1 < len(RECORDER_STANDARDS["NB1"]["Debinder"]) else (None, None)
                            fig_deb = go.Figure(go.Scatter(x=df_deb["DateTime"], y=df_deb[f"Zone #{i}"], name=f"Zone #{i} (Max)", mode="lines", line=dict(color=zone_colors[i-1], width=2)))
                            add_paq_overlay(fig_deb, df_paq, probe_cols, invalid_cols)
                            apply_industrial_style(fig_deb, "Temperature (°C)", y_range=[0, 650], std_min=std_min, std_max=std_max, ts=df_deb["DateTime"])
                            add_zone_backgrounds(fig_deb, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                            charts_to_render.append({"title": f"Debinder Zone #{i}", "fig": fig_deb})
                        fig_comb = go.Figure(go.Scatter(x=df_deb["DateTime"], y=df_deb["Combustion Air Temp"], name="Comb Air (Max)", mode="lines", line=dict(color="#00E5FF", width=2, dash="dash")))
                        add_paq_overlay(fig_comb, df_paq, probe_cols, invalid_cols); apply_industrial_style(fig_comb, "Comb Air (°C)", y_range=[0, 150]); add_zone_backgrounds(fig_comb, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                        charts_to_render.append({"title": "Combustion Air Temp", "fig": fig_comb})
                    else:
                        fig_deb = make_subplots(specs=[[{"secondary_y": True}]])
                        for i in range(1, 5): fig_deb.add_trace(go.Scatter(x=df_deb["DateTime"], y=df_deb[f"Zone #{i}"], name=f"Zone #{i} (Max)", mode="lines", line=dict(color=zone_colors[i-1], width=2)), secondary_y=False)
                        fig_deb.add_trace(go.Scatter(x=df_deb["DateTime"], y=df_deb["Combustion Air Temp"], name="Comb Air (Max)", mode="lines", line=dict(color="#00E5FF", width=2, dash="dash")), secondary_y=True)
                        add_paq_overlay(fig_deb, df_paq, probe_cols, invalid_cols, is_dual_axis=True); add_zone_backgrounds(fig_deb, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                        fig_deb.update_layout(hovermode="x unified", height=450, margin=dict(l=60, r=180, t=30, b=40), yaxis=dict(range=[0, 650], title="Temperature (°C)"), yaxis2=dict(title="Comb Air (°C)", overlaying="y", side="right", range=[0, 150]))
                        charts_to_render.append({"title": "Debinder Zones", "fig": fig_deb})
                    
                    render_combined_charts_vertically(charts_to_render, zoom_mode, zoom_x_range, "deb")
                    st.markdown("---")
                    df_merged = pd.merge(df_deb.rename(columns={'DateTime': 'Sync_DateTime'}), df_paq[['Sync_DateTime'] + [c for c in probe_cols if c in df_paq.columns]], on='Sync_DateTime', how='outer').sort_values('Sync_DateTime')
                    st.download_button(label="📊 Download Combined Data (.xlsx)", data=to_excel_bytes(df_merged), file_name="Combined_Debinder_Datapaq.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, type="primary")

            # Combine: NB3 (.CSV)
            if rec_csv_files and furnace_id == "NB3":
                df_nb3 = process_nb3_files(rec_csv_files, expected_furnace="NB3")
                if not df_nb3.empty:
                    st.success("✅ Recorder files uploaded successfully! Generating Combined Overlay Charts...")
                    fixed_y_range, charts_to_render = [0, 650], []
                    split_charts = st.toggle("📊 แยกกราฟ Top / Bottom / Dryer เป็นรายโซนย่อย", key="split_cmb_csv")
                    top_colors, bottom_colors, dry_colors = ["#FF0000", "#008000", "#0000FF", "#8A2BE2", "#A52A2A", "#FFA500", "#9ACD32"], ["#00BFFF", "#FF1493", "#808080", "#00FF00", "#008000", "#0000FF", "#8A2BE2"], ["#FFA500", "#9ACD32", "#008B8B"]
                    dryoff_names = ["DRYOFF1", "DRYOFF2", "DRYOFF3"]
                    
                    if split_charts:
                        for i in range(1, 8):
                            if f"Top Zone #{i}" in df_nb3.columns:
                                std_min, std_max = RECORDER_STANDARDS["NB3"]["Top"][i-1] if i-1 < len(RECORDER_STANDARDS["NB3"]["Top"]) else (None, None)
                                fig = go.Figure(go.Scatter(x=df_nb3["DateTime"], y=df_nb3[f"Top Zone #{i}"], name=f"Top Zone #{i}", mode="lines", line=dict(color=top_colors[i-1], width=2)))
                                add_paq_overlay(fig, df_paq, probe_cols, invalid_cols); apply_industrial_style(fig, "Temperature (°C)", y_range=fixed_y_range, std_min=std_min, std_max=std_max, ts=df_nb3["DateTime"]); add_zone_backgrounds(fig, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                                charts_to_render.append({"title": f"Top Zone #{i}", "fig": fig})
                        for i in range(1, 8):
                            if f"Bottom Zone #{i}" in df_nb3.columns:
                                std_min, std_max = RECORDER_STANDARDS["NB3"]["Bottom"][i-1] if i-1 < len(RECORDER_STANDARDS["NB3"]["Bottom"]) else (None, None)
                                fig = go.Figure(go.Scatter(x=df_nb3["DateTime"], y=df_nb3[f"Bottom Zone #{i}"], name=f"Bottom Zone #{i}", mode="lines", line=dict(color=bottom_colors[i-1], width=2)))
                                add_paq_overlay(fig, df_paq, probe_cols, invalid_cols); apply_industrial_style(fig, "Temperature (°C)", y_range=fixed_y_range, std_min=std_min, std_max=std_max, ts=df_nb3["DateTime"]); add_zone_backgrounds(fig, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                                charts_to_render.append({"title": f"Bottom Zone #{i}", "fig": fig})
                        for i in range(1, 4):
                            if dryoff_names[i-1] in df_nb3.columns:
                                std_min, std_max = RECORDER_STANDARDS["NB3"]["Dryer"][i-1] if i-1 < len(RECORDER_STANDARDS["NB3"]["Dryer"]) else (None, None)
                                fig = go.Figure(go.Scatter(x=df_nb3["DateTime"], y=df_nb3[dryoff_names[i-1]], name=dryoff_names[i-1], mode="lines", line=dict(color=dry_colors[i-1], width=2)))
                                add_paq_overlay(fig, df_paq, probe_cols, invalid_cols); apply_industrial_style(fig, "Temperature (°C)", y_range=fixed_y_range, std_min=std_min, std_max=std_max, ts=df_nb3["DateTime"]); add_zone_backgrounds(fig, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                                charts_to_render.append({"title": f"{dryoff_names[i-1]}", "fig": fig})
                    else:
                        fig1 = go.Figure()
                        for i in range(1, 8):
                            if f"Top Zone #{i}" in df_nb3.columns: fig1.add_trace(go.Scatter(x=df_nb3["DateTime"], y=df_nb3[f"Top Zone #{i}"], name=f"Top Zone #{i}", mode="lines", line=dict(color=top_colors[i-1], width=2)))
                        add_paq_overlay(fig1, df_paq, probe_cols, invalid_cols); apply_industrial_style(fig1, "Temperature (°C)", y_range=fixed_y_range); add_zone_backgrounds(fig1, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                        charts_to_render.append({"title": "1) Top Zones", "fig": fig1})

                        fig2 = go.Figure()
                        for i in range(1, 8):
                            if f"Bottom Zone #{i}" in df_nb3.columns: fig2.add_trace(go.Scatter(x=df_nb3["DateTime"], y=df_nb3[f"Bottom Zone #{i}"], name=f"Bottom Zone #{i}", mode="lines", line=dict(color=bottom_colors[i-1], width=2)))
                        add_paq_overlay(fig2, df_paq, probe_cols, invalid_cols); apply_industrial_style(fig2, "Temperature (°C)", y_range=fixed_y_range); add_zone_backgrounds(fig2, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                        charts_to_render.append({"title": "2) Bottom Zones", "fig": fig2})

                        fig3 = go.Figure()
                        for i in range(1, 4):
                            if dryoff_names[i-1] in df_nb3.columns: fig3.add_trace(go.Scatter(x=df_nb3["DateTime"], y=df_nb3[dryoff_names[i-1]], name=dryoff_names[i-1], mode="lines", line=dict(color=dry_colors[i-1], width=2)))
                        add_paq_overlay(fig3, df_paq, probe_cols, invalid_cols); apply_industrial_style(fig3, "Temperature (°C)", y_range=fixed_y_range); add_zone_backgrounds(fig3, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                        charts_to_render.append({"title": "3) DRYOFF", "fig": fig3})
                    
                    fig4 = make_subplots(specs=[[{"secondary_y": True}]])
                    if "Oxygen EXIT" in df_nb3.columns: fig4.add_trace(go.Scatter(x=df_nb3["DateTime"], y=df_nb3["Oxygen EXIT"], name="Oxygen EXIT", mode="lines", line=dict(color="#FF00FF", width=2)), secondary_y=False)
                    if "Oxygen ENTRANCE" in df_nb3.columns: fig4.add_trace(go.Scatter(x=df_nb3["DateTime"], y=df_nb3["Oxygen ENTRANCE"], name="Oxygen ENTRANCE", mode="lines", line=dict(color="#A52A2A", width=2)), secondary_y=False)
                    if "N2 Exit" in df_nb3.columns: fig4.add_trace(go.Scatter(x=df_nb3["DateTime"], y=df_nb3["N2 Exit"], name="N2 Exit", mode="lines", line=dict(color="#1f77b4", width=2, dash="dash")), secondary_y=True)
                    if "N2 Entrance" in df_nb3.columns: fig4.add_trace(go.Scatter(x=df_nb3["DateTime"], y=df_nb3["N2 Entrance"], name="N2 Entrance", mode="lines", line=dict(color="#2ca02c", width=2, dash="dash")), secondary_y=True)
                    add_paq_overlay(fig4, df_paq, probe_cols, invalid_cols, is_dual_axis=True); apply_industrial_style(fig4, "Oxygen (ppm) / PAQ (°C)", is_dual_axis=True); fig4.update_layout(yaxis=dict(title=dict(text="Oxygen (ppm) / PAQ (°C)"), range=[0, 650], showgrid=True), yaxis2=dict(title=dict(text="N2 Flow Rate [0-1000]"), showgrid=False, overlaying="y", side="right", range=[0, 1000])); add_zone_backgrounds(fig4, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                    charts_to_render.append({"title": "4) O2 & N2 Flow", "fig": fig4})

                    fig5 = go.Figure()
                    if "COOL WATER TEMP" in df_nb3.columns: fig5.add_trace(go.Scatter(x=df_nb3["DateTime"], y=df_nb3["COOL WATER TEMP"], name="COOL WATER TEMP", mode="lines", line=dict(color="#008B8B", width=2)))
                    add_paq_overlay(fig5, df_paq, probe_cols, invalid_cols); apply_industrial_style(fig5, "Temperature (°C)", y_range=[-150, 650]); add_zone_backgrounds(fig5, zones, paq_start_dt, data1['detected_start_sec'], data1['line_speed_mpm'])
                    charts_to_render.append({"title": "5) COOL WATER", "fig": fig5})
                    
                    render_combined_charts_vertically(charts_to_render, zoom_mode, zoom_x_range, "nb3")
                    st.markdown("---")
                    df_merged = pd.merge(df_nb3.rename(columns={'DateTime': 'Sync_DateTime'}), df_paq[['Sync_DateTime'] + [c for c in probe_cols if c in df_paq.columns]], on='Sync_DateTime', how='outer').sort_values('Sync_DateTime')
                    st.download_button(label="📊 Download Combined Data (.xlsx)", data=to_excel_bytes(df_merged), file_name="Combined_NB3_Datapaq.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, type="primary")

# ---------------------------------------------------------
# TAB 3: FURNACE PRODUCT & SIMULATION
# ---------------------------------------------------------
with tabs[3]:
    st.header("🏭 Furnace Product & Simulation")
    st.markdown("ระบบจำลองตำแหน่งชิ้นงานในเตาอบประสาน (Brazing Furnace) โดยอ้างอิงจากแผนการโหลดชิ้นงานจริง")

    st.markdown("### 📥 1. อัปโหลดแผนการผลิต (Excel)")

    col_up1, col_up2 = st.columns([4, 1])
    with col_up1:
        uploaded_excels = st.file_uploader(
            "อัปโหลดไฟล์ข้อมูลแผนการผลิตของเตา (.xlsx หรือ .xls สามารถเลือกหลายไฟล์พร้อมกันได้)", 
            type=["xlsx", "xls"], 
            accept_multiple_files=True,
            key=st.session_state["file_uploader_key"]
        )

    with col_up2:
        st.write(""); st.write("")
        if st.button("🗑️ Reset / Clear Data", key="reset_sim_data", use_container_width=True):
            st.session_state["file_uploader_key"] = str(datetime.now().timestamp())
            st.rerun()

    df_schedule_raw = pd.DataFrame()
    current_nb_detected_excel = None

    if uploaded_excels:
        st.success(f"✅ อัปโหลดไฟล์ Excel สำเร็จจำนวน {len(uploaded_excels)} ไฟล์")
        dfs = []
        for file in uploaded_excels:
            try: dfs.append(pd.read_excel(file))
            except Exception as e: st.error(f"ไม่สามารถอ่านไฟล์ {file.name} ได้: {e}")
                
        if dfs:
            df_schedule_raw = pd.concat(dfs, ignore_index=True)
            current_nb_detected_excel = detect_furnace_from_dataframe(df_schedule_raw)

    st.markdown("---")

    st.markdown("### ⚙️ 2. ตั้งค่าพารามิเตอร์เตา")
    col1, col2 = st.columns(2)

    with col1:
        auto_detected_nb = current_nb_detected_paq or current_nb_detected_excel
        if auto_detected_nb:
            source_msg = ".PAQ" if current_nb_detected_paq else "Excel"
            st.info(f"🔥 ระบบตรวจพบเตาจากไฟล์ {source_msg}: **{auto_detected_nb}**")
            current_nb = auto_detected_nb
        else:
            current_nb = st.selectbox("🔥 เลือกเตา (Manual):", ["NB1", "NB2", "NB3"], index=2)

    default_speeds = {"NB1": 1.40, "NB2": 1.56, "NB3": 1.27}
    default_speed_for_current_nb = default_speeds.get(current_nb, 1.40)
    
    if data1 and "line_speed_mpm" in data1 and current_nb_detected_paq == current_nb:
        default_speed_for_current_nb = float(data1["line_speed_mpm"])

    with col2:
        belt_speed_m_min = st.number_input(
            "ความเร็วสายพาน (เมตร/นาที)", min_value=0.1, max_value=5.0, 
            value=default_speed_for_current_nb, step=0.01, format="%.2f"
        )
        belt_speed_ms = belt_speed_m_min / 60.0  
        st.caption("ℹ️ *ระยะห่าง (Pitch) และการจัดเรียงถูกคำนวณอัตโนมัติจากฐานข้อมูลตามรุ่น*")

    st.markdown("---")

    zones = FURNACE_ZONE_DATA[current_nb]
    cumulative_len = 0
    furnace_zones_df = []
    for z in zones:
        start = cumulative_len
        end = cumulative_len + z["len"]
        furnace_zones_df.append({ "Name": z["name"], "Type": z["type"], "Length": z["len"], "Start": start, "End": end })
        cumulative_len = end

    total_furnace_length = cumulative_len
    df_zones = pd.DataFrame(furnace_zones_df)
    all_zone_labels = df_zones["Name"].tolist()
    df_pieces = pd.DataFrame()

    if not df_schedule_raw.empty:
        required_cols = ['Description', 'Quantity', 'Start Time']
        if all(col in df_schedule_raw.columns for col in required_cols):
            df_schedule = df_schedule_raw.dropna(subset=['Start Time', 'Quantity']).copy()
            df_schedule = df_schedule[df_schedule['Quantity'] > 0]
            df_schedule['Start Time'] = pd.to_datetime(df_schedule['Start Time'])
            df_schedule = df_schedule.sort_values('Start Time')
            
            preview_cols = required_cols.copy()
            if 'Reference' in df_schedule.columns: preview_cols.insert(0, 'Reference')
            if 'WORKCENTERLIST' in df_schedule.columns: preview_cols.append('WORKCENTERLIST')
                
            with st.expander("ดูข้อมูลแผนการผลิต (Data Preview)"):
                st.dataframe(df_schedule[preview_cols].head(50), use_container_width=True)
                
            pieces_list = []
            next_available_time = None  
            
            for _, row in df_schedule.iterrows():
                qty, start_t, desc = int(row['Quantity']), row['Start Time'], str(row['Description'])
                desc_upper = desc.upper()
                ref = str(row['Reference']) if 'Reference' in df_schedule.columns else ""
                
                model_start_offset = 0.0
                if current_nb == "NB3":
                    if any(kw in desc_upper for kw in ["BTM", "CORION", "A669223C"]):
                        for z in FURNACE_ZONE_DATA["NB3"]:
                            if z["name"] in ["Entrance", "Fluxer"]: model_start_offset += z["len"]
                        model_start_offset += 0.001 

                pitch_m, pieces_per_pitch = get_model_info(desc, current_nb)
                interval_s = pitch_m / belt_speed_ms
                rows_to_load = int(math.ceil(qty / pieces_per_pitch))
                
                if next_available_time is None or start_t > next_available_time: current_load_time = start_t
                else: current_load_time = next_available_time
                
                for i in range(rows_to_load):
                    pieces_list.append({
                        'Reference': ref, 'Model': desc, 'LoadTime': current_load_time,
                        'Pitch_m': pitch_m, 'Speed_ms': belt_speed_ms, 'Pieces_in_Box': pieces_per_pitch,
                        'Start_Offset_m': model_start_offset
                    })
                    current_load_time += pd.Timedelta(seconds=interval_s)
                next_available_time = current_load_time
            
            df_pieces = pd.DataFrame(pieces_list)
            if not df_pieces.empty:
                df_pieces = df_pieces.sort_values('LoadTime').reset_index(drop=True)
                df_pieces['Remaining_Dist'] = total_furnace_length - df_pieces['Start_Offset_m']
                df_pieces['ExitTime'] = df_pieces['LoadTime'] + pd.to_timedelta(df_pieces['Remaining_Dist'] / df_pieces['Speed_ms'], unit='s')
                df_pieces['Display_Model'] = df_pieces.apply(lambda x: f"{x['Model']} ({x['Reference']})" if pd.notna(x.get('Reference')) and str(x.get('Reference')).strip() not in ["", "nan"] else x['Model'], axis=1)
        else:
            st.error(f"❌ ไฟล์ Excel ต้องมีคอลัมน์ต่อไปนี้: {', '.join(required_cols)}")

    fig = go.Figure()
    for idx, row in df_zones.iterrows():
        fig.add_shape(type="rect", x0=row["Start"], x1=row["End"], y0=0, y1=1, fillcolor=ZONE_COLORS.get(row["Type"], "#ccc"), line=dict(color="white", width=1), layer="below")
        fig.add_annotation(x=(row["Start"] + row["End"]) / 2, y=0.5, text=row["Name"], showarrow=False, textangle=-90, font=dict(size=11, color="black" if row["Type"] in ["Dryer", "Xfer", "Cooling"] else "white"))

    fig.add_shape(type="line", x0=0, x1=total_furnace_length, y0=1.2, y1=1.2, line=dict(color="gray", width=2, dash="dot"), layer="below")
    df_current = pd.DataFrame()

    if not df_pieces.empty:
        min_time = df_pieces['LoadTime'].min()
        max_time = df_pieces['LoadTime'].max() + pd.Timedelta(minutes=90) 
        min_dt, max_dt = min_time.to_pydatetime(), max_time.to_pydatetime()
        
        if 'current_sim_time' not in st.session_state or st.session_state.current_sim_time < min_dt or st.session_state.current_sim_time > max_dt:
            st.session_state.current_sim_time = min_dt
            st.session_state.date_input_val = min_dt.date()
            st.session_state.time_input_val = min_dt.strftime("%H:%M:%S")
            st.session_state.sim_time_slider = min_dt
            
        current_sim = st.session_state.current_sim_time
        df_pieces['Elapsed_s'] = (pd.to_datetime(current_sim) - df_pieces['LoadTime']).dt.total_seconds()
        df_pieces['Position'] = df_pieces['Start_Offset_m'] + (df_pieces['Elapsed_s'] * df_pieces['Speed_ms'])
        df_current = df_pieces[(df_pieces['Position'] >= df_pieces['Start_Offset_m']) & (df_pieces['Position'] <= total_furnace_length)].copy()
        
        color_sequence = px.colors.qualitative.Plotly
        if not df_current.empty:
            for i, (display_model_name, group) in enumerate(df_current.groupby('Display_Model')):
                customdata = np.stack((group['LoadTime'].dt.strftime('%H:%M:%S'), group['ExitTime'].dt.strftime('%H:%M:%S')), axis=-1)
                fig.add_trace(go.Scatter(
                    x=group['Position'], y=[1.2] * len(group), mode="markers", name=display_model_name, 
                    marker=dict(symbol="square", size=12, color=color_sequence[i % len(color_sequence)], line=dict(width=1, color="black")),
                    hovertemplate=f"<b>{display_model_name}</b><br>ตำแหน่ง: %{{x:.2f}} ม.<br>โหลดเข้า: %{{customdata[0]}}<br>ออกเตา: %{{customdata[1]}}<extra></extra>",
                    customdata=customdata
                ))
    else:
        st.info("💡 **ข้อมูลการโหลดชิ้นงานยังว่างเปล่า** อัปโหลดไฟล์ Excel ด้านบนเพื่อดูตำแหน่งจริงและเวลาที่สัมพันธ์กัน")
        pitch_m = 0.660
        product_positions = np.arange(0.0, total_furnace_length, pitch_m)
        fig.add_trace(go.Scatter(x=product_positions, y=[1.2] * len(product_positions), mode="markers", name="ตัวอย่าง (Sample Data)", marker=dict(symbol="square", size=12, color="#32CD32", line=dict(width=2, color="black")), hovertemplate="ตำแหน่ง: %{x:.2f} เมตร<extra></extra>"))

    img_file_sim = IMAGE_MAPPING.get(current_nb)
    y_range = [-0.2, 1.8] 

    if img_file_sim and os.path.exists(img_file_sim):
        img = Image.open(img_file_sim)
        fig.add_layout_image(dict(source=img, xref="x", yref="y", x=0, y=3.2, sizex=total_furnace_length, sizey=1.6, sizing="stretch", opacity=1, layer="above"))
        y_range = [-0.2, 3.5]

    fig.update_layout(title=f"Furnace Timeline: {current_nb} (Total Length: {total_furnace_length:.2f} m)", xaxis=dict(title="Distance (Meters)", range=[0, total_furnace_length], tickmode="linear", tick0=0, dtick=2), yaxis=dict(visible=False, range=y_range), height=550, margin=dict(l=20, r=20, t=50, b=120), template="plotly_white", hovermode="x unified", showlegend=True, legend=dict(orientation="h", yanchor="top", y=-0.25, xanchor="center", x=0.5))
    st.plotly_chart(fig, use_container_width=True)

    if not df_pieces.empty:
        st.markdown("---")
        st.markdown("### ⏱️ ควบคุมเวลาจำลอง (Simulation Time)")
        
        def on_slider_change():
            new_dt = st.session_state.sim_time_slider
            st.session_state.current_sim_time = new_dt
            st.session_state.date_input_val = new_dt.date()
            st.session_state.time_input_val = new_dt.strftime("%H:%M:%S")

        def on_input_change():
            try:
                d, t_str = st.session_state.date_input_val, st.session_state.time_input_val
                t = pd.to_datetime(t_str, format="%H:%M:%S").time()
                new_dt = datetime.combine(d, t)
                if new_dt < min_dt: new_dt = min_dt
                if new_dt > max_dt: new_dt = max_dt
                st.session_state.current_sim_time = new_dt
                st.session_state.sim_time_slider = new_dt
                st.session_state.date_input_val = new_dt.date()
                st.session_state.time_input_val = new_dt.strftime("%H:%M:%S")
            except ValueError: pass 
                
        col_d, col_t = st.columns(2)
        with col_d: st.date_input("📅 เลือกวันที่ (Date)", min_value=min_dt.date(), max_value=max_dt.date(), key="date_input_val", on_change=on_input_change)
        with col_t: st.text_input("⏰ ป้อนเวลา (Time) เช่น 19:32:00", key="time_input_val", on_change=on_input_change, help="กรุณาป้อนเวลาในรูปแบบ ชั่วโมง:นาที:วินาที (HH:MM:SS) ตัวอย่าง: 19:32:00")
        try: pd.to_datetime(st.session_state.time_input_val, format="%H:%M:%S")
        except ValueError: st.error("⚠️ รูปแบบเวลาไม่ถูกต้อง! กรุณาป้อนเวลาในรูปแบบ HH:MM:SS (เช่น 19:32:00)")

        st.slider("ลากเพื่อเลื่อนดูเวลาจำลอง (Slide to Simulator Time):", min_value=min_dt, max_value=max_dt, step=timedelta(seconds=1), format="YYYY-MM-DD HH:mm:ss", key="sim_time_slider", on_change=on_slider_change)
        
        st.markdown(f"### 📋 รายละเอียดชิ้นงานรายโซน ณ เวลา **{st.session_state.current_sim_time.strftime('%Y-%m-%d %H:%M:%S')}**")
        
        if not df_current.empty:
            bins = [0] + df_zones["End"].tolist()
            df_current['Zone'] = pd.cut(df_current['Position'], bins=bins, labels=all_zone_labels, right=True)
            df_current['Display_Model_Table'] = df_current.apply(lambda x: f"{x['Model']}\n{x['Reference']}" if pd.notna(x.get('Reference')) and str(x.get('Reference')).strip() not in ["", "nan"] else x['Model'], axis=1)
            
            wip_summary = df_current.groupby(['Zone', 'Display_Model_Table'], observed=False).agg(Box_Count=('Display_Model_Table', 'size'), Multiplier=('Pieces_in_Box', 'first')).reset_index()
            wip_summary = wip_summary[wip_summary['Box_Count'] > 0]
            wip_summary['Quantity'] = wip_summary['Box_Count'] * wip_summary['Multiplier']
            wip_pivot = wip_summary.pivot(index='Display_Model_Table', columns='Zone', values='Quantity').fillna(0).astype(int)
            wip_pivot.index.name = 'Model (Reference)'
            wip_pivot = wip_pivot.reindex(columns=all_zone_labels, fill_value=0)
            
            wip_pivot.loc['Total (รวม)'] = wip_pivot.sum(numeric_only=True)
            grand_total = int(wip_pivot.loc['Total (รวม)'].sum())
            
            st.success(f"📌 **มีชิ้นงานในกระบวนการเตาทั้งหมด ณ เวลานี้: {grand_total:,} ชิ้น**")

            def highlight_nonzero(val): return 'background-color: #E8E8E8; color: #000000; font-weight: bold;' if isinstance(val, (int, float)) and val > 0 else ''
            def highlight_total_row(row): return ['background-color: #FFF2CC; font-weight: bold; color: #000000'] * len(row) if row.name == 'Total (รวม)' else [''] * len(row)
                
            if hasattr(wip_pivot.style, 'map'): styled_pivot = (wip_pivot.style.map(highlight_nonzero).apply(highlight_total_row, axis=1).format(precision=0))
            else: styled_pivot = (wip_pivot.style.applymap(highlight_nonzero).apply(highlight_total_row, axis=1).format(precision=0))
            st.dataframe(styled_pivot, use_container_width=True)
        else:
            empty_df = pd.DataFrame(columns=all_zone_labels)
            empty_df.index.name = 'Model (Reference)'
            st.dataframe(empty_df, use_container_width=True)
            wip_summary = pd.DataFrame(columns=['Zone', 'Display_Model_Table', 'Box_Count', 'Multiplier', 'Quantity'])

        st.markdown("### 📊 สรุปจำนวนชิ้นงานตามกลุ่มกระบวนการ (Process Group Summary)")
        zone_type_mapping = {}
        for z in FURNACE_ZONE_DATA[current_nb]:
            zone_type_mapping[z['name']] = z['name'] if "XFER" in z['name'].upper() else z['type']
        
        display_type_names = {"Entrance": "🚪 Entrance (หน้าเตา)", "Heating": "🔥 Brazing Zone (Z#1 - Z#7)", "Dryer": "💨 Dryer Zone", "Debinder": "♨️ Debinder Zone", "Cooling": "❄️ Cooling Zone", "Flux": "💧 Flux Zone", "Exit": "🏁 Exit (ท้ายเตา)"}
        
        ordered_types = []
        for z in FURNACE_ZONE_DATA[current_nb]:
            t = zone_type_mapping[z['name']]
            if t not in ordered_types: ordered_types.append(t)
            if t not in display_type_names: display_type_names[t] = f"↔️ {t} (จุดเชื่อมต่อ)"
                
        ordered_display_groups = [display_type_names[t] for t in ordered_types]
        
        if not wip_summary.empty:
            wip_summary['Process_Group_Raw'] = wip_summary['Zone'].map(zone_type_mapping)
            wip_summary['Process_Group'] = wip_summary['Process_Group_Raw'].map(display_type_names)
            group_summary = wip_summary.groupby(['Process_Group', 'Display_Model_Table'], observed=False).agg(Quantity=('Quantity', 'sum'), Box_Count=('Box_Count', 'sum')).reset_index()
            group_summary = group_summary[group_summary['Quantity'] > 0]
        else: group_summary = pd.DataFrame(columns=['Process_Group', 'Display_Model_Table', 'Quantity', 'Box_Count'])
        
        if not group_summary.empty:
            chart_data = group_summary.groupby('Process_Group', observed=False).agg(Quantity=('Quantity', 'sum'), Box_Count=('Box_Count', 'sum')).reset_index()
            chart_data['Process_Group'] = pd.Categorical(chart_data['Process_Group'], categories=ordered_display_groups, ordered=True)
            chart_data = chart_data.sort_values('Process_Group')
            
            fig_bar = px.bar(chart_data, x='Process_Group', y='Quantity', text='Quantity', labels={'Process_Group': '', 'Quantity': 'จำนวนชิ้นงาน (ชิ้น)'}, color='Quantity', color_continuous_scale=px.colors.sequential.Blues)
            fig_bar.update_traces(texttemplate='<b>%{text} ชิ้น</b>', textposition='outside', hovertemplate='<b>%{x}</b><br>จำนวน: %{y} ชิ้น<extra></extra>', marker_line_color='rgb(8,48,107)', marker_line_width=1.5, opacity=0.85)
            fig_bar.update_layout(template='plotly_white', height=400, margin=dict(t=30, b=50, l=20, r=20), xaxis=dict(tickangle=-45, title_font=dict(size=14)), yaxis=dict(title="จำนวน (ชิ้น)", showgrid=True, gridcolor='#E5E5E5'), coloraxis_showscale=False)
            max_qty = chart_data['Quantity'].max()
            fig_bar.update_yaxes(range=[0, max_qty * 1.2])
            st.plotly_chart(fig_bar, use_container_width=True)

        if len(ordered_display_groups) > 0:
            cols = st.columns(3)
            for idx, p_group in enumerate(ordered_display_groups):
                col = cols[idx % 3]
                with col:
                    df_pg = group_summary[group_summary['Process_Group'] == p_group]
                    total_qty = int(df_pg['Quantity'].sum()) if not df_pg.empty else 0
                    total_pitches = int(df_pg['Box_Count'].sum()) if not df_pg.empty else 0
                    
                    with st.container(border=True):
                        st.markdown(f"**{p_group}**")
                        if total_qty > 0:
                            st.markdown(f"### รวม: {total_qty} ชิ้น ({total_pitches} pitches)")
                            for _, r in df_pg.iterrows():
                                model_name_inline = r['Display_Model_Table'].replace('\n', ' ')
                                qty, pitches = int(r['Quantity']), int(r['Box_Count'])
                                st.caption(f"• {model_name_inline} : {qty} ชิ้น ({pitches} pitches)")
                        else:
                            st.markdown("### รวม: 0 ชิ้น")
                            st.caption("ไม่มีชิ้นงาน")
        else: st.info("ไม่มีกระบวนการหลักในเตานี้")
