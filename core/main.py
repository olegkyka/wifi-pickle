from logging import getLogger,ERROR
getLogger('scapy.runtime').setLevel(ERROR)
from PyQt4 import QtGui
from PyQt4 import QtCore
from json import dumps,loads
from pwd import getpwnam
from grp import getgrnam
from time import asctime
from shutil import move
from re import search,sub
from platform import dist
from netaddr import EUI
from collections import OrderedDict
from shlex import split

from compat import *

from os import (
    system, path, getcwd, popen, listdir, mkdir, chown
)
from subprocess import (
    Popen, PIPE, call, check_output
)

from core.utils import (
    Refactor, set_monitor_mode, waiterSleepThread, setup_logger, is_ascii, is_hexadecimal, exec_bash, del_item_folder
)
from core.widgets.tabmodels import (
    Mitmproxy, PickleMonitor, PickleSettings, PacketsSniffer, ImageCapture, StatusAccessPoint
)

from core.widgets.popupmodels import (
    PopUpPlugins
)

from core.utility.threads import  (
    ProcessHostapd, ThRunDhcp, ProcessThread, ThreadReactor, ThreadPopen, ThreadMitmProxy
)

from core.widgets.customiseds import AutoTableWidget
from plugins.external.scripts import *
import modules as GUIModules
from core.helpers.about import frmAbout
from core.helpers.update import frm_githubUpdate
from core.utility.settings import frm_Settings
import core.utility.constants as C
from core.helpers.update import ProgressBarWid
from core.helpers.report import frm_ReportLogger
from core.widgets.notifications import ServiceNotify
from isc_dhcp_leases.iscdhcpleases import IscDhcpLeases
from netfilterqueue import NetfilterQueue
from core.servers.proxy.tcp.intercept import ThreadSniffingPackets
import emoji
#from mitmproxy import proxy, flow, options
#from mitmproxy.proxy.server import ProxyServer

"""
Description:
    This program is a core for wifi-pickle.py. file which includes functionality
    for mount Access point.

Copyright:
    Copyright (C) 2018-2019 Shane W. Scott GoVanguard Inc.
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>
"""


author      = 'Shane Scott, GoVanguard'
emails      = ['hello@gvit.com']
license     = ' GNU GPL 3'
version     = '0.3.2'
update      = '11/04/2018' # This is the USA :D
desc        = ['A salty tool for Rogue Wi-Fi Access Point Attacks']

class Initialize(QtGui.QMainWindow):
    ''' Main window settings multi-window opened'''
    def __init__(self, parent=None):
        super(Initialize, self).__init__(parent)
        self.FSettings      = frm_Settings()
        self.form_widget    = WifiPickle(self)
        #for exclude USB adapter if the option is checked in settings tab
        self.networkcontrol = None
        # create advanced mode support
        dock = QtGui.QDockWidget()
        dock.setTitleBarWidget(QtGui.QWidget())
        dock.setWidget(self.form_widget)
        dock.setSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        dock.setFeatures(QtGui.QDockWidget.NoDockWidgetFeatures)
        dock.setAllowedAreas(QtCore.Qt.AllDockWidgetAreas)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock)
        # set window title
        self.setWindowTitle(emoji.emojize('WiFi-Pickle :cucumber: 0.3.2'))
        self.setGeometry(0, 0, C.GEOMETRYH, C.GEOMETRYW) # set geometry window
        self.loadtheme(self.FSettings.get_theme_qss())

    def loadtheme(self,theme):
        ''' load Theme from file .qss '''
        sshFile=("core/%s.qss"%(theme))
        with open(sshFile,"r") as fh:
            self.setStyleSheet(fh.read())

    def center(self):
        ''' set Window center desktop '''
        frameGm = self.frameGeometry()
        centerPoint = QtGui.QDesktopWidget().availableGeometry().center()
        frameGm.moveCenter(centerPoint)
        self.move(frameGm.topLeft())

    def closeEvent(self, event):
        ''' When the user clicks on the X button '''
        if self.form_widget.THReactor.isRunning():
            self.form_widget.THReactor.stop()

        # remove card apdater from network-manager conf
        if not self.form_widget.FSettings.Settings.get_setting(
            'accesspoint','persistNetwokManager',format=bool):
            if self.networkcontrol != None:
                self.networkcontrol.remove_settingsNM()

        # check if any wireless card is enable as Monitor mode
        iwconfig = Popen(['iwconfig'], stdout=PIPE,shell=False,stderr=PIPE)
        for i in iwconfig.stdout.readlines():
            if search('Mode:Monitor',i.decode()):
                self.reply = QtGui.QMessageBox.question(self,
                'About Exit','Are you sure to quit?', QtGui.QMessageBox.Yes |
                QtGui.QMessageBox.No, QtGui.QMessageBox.No)
                if self.reply == QtGui.QMessageBox.Yes:
                    set_monitor_mode(i.split()[0]).setDisable()
                    return event.accept()
                return event.ignore()

        # check is Rouge AP is running
        if self.form_widget.Apthreads['RougeAP'] != []:
            self.reply = QtGui.QMessageBox.question(self,
            'About Access Point','Are you sure to stop all threads AP ?', QtGui.QMessageBox.Yes |
            QtGui.QMessageBox.No, QtGui.QMessageBox.No)
            if self.reply == QtGui.QMessageBox.Yes:
                print('killing all threads...')
                self.form_widget.stop_access_point()
                return event.accept()
            return event.ignore()
        return event.accept()

class WifiPickle(QtGui.QWidget):
    ''' load main window class'''
    def __init__(self, mainWindow):
        QtGui.QWidget.__init__(self)
        self.mainWindow = mainWindow
        self.InternetShareWiFi = True # share internet options

        # define all Widget TABs
        self.MainControl    = QtGui.QVBoxLayout()
        self.TabControl     = QtGui.QTabWidget()
        self.Tab_Default    = QtGui.QWidget()
        self.Tab_MitmProxy  = QtGui.QWidget()
        self.Tab_Packetsniffer = QtGui.QWidget()
        self.Tab_statusAP   = QtGui.QWidget()
        self.Tab_imageCap   = QtGui.QWidget()
        self.Tab_Settings   = QtGui.QWidget()
        self.Tab_ApMonitor  = QtGui.QWidget()
        self.Tab_Plugins    = QtGui.QWidget()
        self.Tab_dock       = QtGui.QMainWindow() # for dockarea
        self.FSettings      = self.mainWindow.FSettings

        # create dockarea in Widget class
        self.dock = QtGui.QDockWidget()
        self.dock.setTitleBarWidget(QtGui.QWidget())
        self.dock.setSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        self.dock.setFeatures(QtGui.QDockWidget.NoDockWidgetFeatures)
        self.dock.setAllowedAreas(QtCore.Qt.AllDockWidgetAreas)

        # icons menus left widgets
        self.TabListWidget_Menu = QtGui.QListWidget()
        self.item_home = QtGui.QListWidgetItem()
        self.item_home.setText('Home')
        self.item_home.setSizeHint(QtCore.QSize(30,30))
        self.item_home.setIcon(QtGui.QIcon('icons/pickle2.png'))
        self.TabListWidget_Menu.addItem(self.item_home)

        self.item_settings = QtGui.QListWidgetItem()
        self.item_settings.setText('Settings')
        self.item_settings.setSizeHint(QtCore.QSize(30,30))
        self.item_settings.setIcon(QtGui.QIcon('icons/settings-AP.png'))
        self.TabListWidget_Menu.addItem(self.item_settings)

        self.item_plugins =QtGui.QListWidgetItem()
        self.item_plugins.setText('Plugins')
        self.item_plugins.setSizeHint(QtCore.QSize(30,30))
        self.item_plugins.setIcon(QtGui.QIcon('icons/plugins-new.png'))
        self.TabListWidget_Menu.addItem(self.item_plugins)

        self.item_mitmProxy = QtGui.QListWidgetItem()
        self.item_mitmProxy.setText('MITM-Proxy')
        self.item_mitmProxy.setSizeHint(QtCore.QSize(30,30))
        self.item_mitmProxy.setIcon(QtGui.QIcon('icons/mac.png'))
        self.TabListWidget_Menu.addItem(self.item_mitmProxy)

        self.item_packetsniffer = QtGui.QListWidgetItem()
        self.item_packetsniffer.setText('TCP-Proxy')
        self.item_packetsniffer.setSizeHint(QtCore.QSize(30,30))
        self.item_packetsniffer.setIcon(QtGui.QIcon('icons/tcpproxy.png'))
        self.TabListWidget_Menu.addItem(self.item_packetsniffer)

        self.item_imageCapture = QtGui.QListWidgetItem()
        self.item_imageCapture.setText('Images-Cap')
        self.item_imageCapture.setSizeHint(QtCore.QSize(30,30))
        self.item_imageCapture.setIcon(QtGui.QIcon('icons/image.png'))
        self.TabListWidget_Menu.addItem(self.item_imageCapture)

        self.item_dock = QtGui.QListWidgetItem()
        self.item_dock.setText('Activity-Monitor')
        self.item_dock.setSizeHint(QtCore.QSize(30,30))
        self.item_dock.setIcon(QtGui.QIcon('icons/activity-monitor.png'))
        self.TabListWidget_Menu.addItem(self.item_dock)

        self.item_monitor = QtGui.QListWidgetItem()
        self.item_monitor.setText('Stations')
        self.item_monitor.setSizeHint(QtCore.QSize(30,30))
        self.item_monitor.setIcon(QtGui.QIcon('icons/stations.png'))
        self.TabListWidget_Menu.addItem(self.item_monitor)

        self.Stack = QtGui.QStackedWidget(self)
        self.Stack.setSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        self.Tab_Default.setSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        self.Stack.addWidget(self.Tab_Default)
        self.TabListWidget_Menu.currentRowChanged.connect(self.set_index_leftMenu)
        self.TabListWidget_Menu.setFixedWidth(140)
        self.TabListWidget_Menu.setStyleSheet(C.MENU_STYLE)
        # add in Tab default widget TABs

        # create Layout for add contents widgets TABs
        self.ContentTabHome    = QtGui.QVBoxLayout(self.Tab_Default)
        self.ContentTabsettings= QtGui.QVBoxLayout(self.Tab_Settings)
        self.ContentTabMitmProxy = QtGui.QVBoxLayout(self.Tab_MitmProxy)
        self.ContentTabPackets = QtGui.QVBoxLayout(self.Tab_Packetsniffer)
        self.ContentImageCap   = QtGui.QHBoxLayout(self.Tab_imageCap)
        self.ContentTabMonitor = QtGui.QVBoxLayout(self.Tab_ApMonitor)
        self.ContentTabPlugins = QtGui.QVBoxLayout(self.Tab_Plugins)
        self.ContentTabStatus  = QtGui.QVBoxLayout(self.Tab_statusAP)
        self.Stack.addWidget(self.Tab_Settings)
        self.Stack.addWidget(self.Tab_Plugins)
        self.Stack.addWidget(self.Tab_MitmProxy)
        self.Stack.addWidget(self.Tab_Packetsniffer)
        self.Stack.addWidget(self.Tab_imageCap)
        self.Stack.addWidget(self.Tab_dock)
        self.Stack.addWidget(self.Tab_ApMonitor)

        self.Apthreads      = {'RougeAP': []}
        self.APclients      = {}
        # settings advanced mode status
        self.AreaDockInfo = {
            'HTTP-Requests': { # netcreds url requests
                'active' : self.FSettings.Settings.get_setting('dockarea',
                'dock_urlmonitor',format=bool),
            },
            'HTTP-Authentication': { # netcreds passwords logins
                'active' : self.FSettings.Settings.get_setting('dockarea',
                'dock_credencials',format=bool),
            },
            'DHCPD': { # dhcps ouput
                'active' : self.FSettings.Settings.get_setting('dockarea',
                'dock_dhcpd',format=bool),
            },
            'MITMProxy': {
                'active' : self.FSettings.Settings.get_setting('dockarea',
                'dock_mitmproxy', format=bool),
            },
            'MeatGlueDNSProxy': {
                'active' : self.FSettings.Settings.get_setting('dockarea',
                'dock_meatglue_proxy',format=bool),
            },
            'Responder': { # plugins responder output
                'active' : self.FSettings.Settings.get_setting('dockarea',
                'dock_Responder',format=bool),
            }
        }
        self.SettingsEnable     = {
        'ProgCheck':[],'AP_iface': None,'PortRedirect': None, 'interface':'None'}
        self.THeaders  = OrderedDict([('IP Address',[]), ('Device Name',[]), ('Mac Address',[]), ('Vendors',[])])
        # load all session saved in file ctg
        self.status_plugin_proxy_name = QtGui.QLabel('') # status name proxy activated
        self.SessionsAP     = loads(str(self.FSettings.Settings.get_setting('accesspoint','sessions')))
        self.PopUpPlugins   = PopUpPlugins(self.FSettings,self) # create popupPlugins
        self.PopUpPlugins.sendSingal_disable.connect(self.get_disable_proxy_status)
        self.THReactor = ThreadReactor() # thread reactor for sslstrip
        #self.window_phishing = GUIModules.frm_PhishingManager()
        self.initial_GUI_loader()

    def initial_GUI_loader(self):
        ''' configure GUI default window '''
        self.default_TAB_Content()
        self.mitmProxy_TAB_Content()
        self.tcpproxy_TAB_Content()
        self.imageCapture_TAB_Content()
        self.settings_TAB_Content()
        self.apMonitor_Tab_Content()
        self.plugins_TAB_Content()
        self.statusAP_TAB_Content()

        self.layout.addLayout(self.StatusAPTAB)  # add info tab in home page
        self.StatusAPTAB.scroll.setFixedHeight(210)
        self.check_plugins_enable() # check plugins activated

        self.myQMenuBar = QtGui.QMenuBar(self)
        Menu_file = self.myQMenuBar.addMenu('&File')
        exportAction = QtGui.QAction('Report Logger...', self)
        deleteAction = QtGui.QAction('Clear Logger', self)
        deleteAction.setIcon(QtGui.QIcon('icons/delete.png'))
        exportAction.setIcon(QtGui.QIcon('icons/export.png'))
        Menu_file.addAction(exportAction)
        Menu_file.addAction(deleteAction)
        deleteAction.triggered.connect(self.clean_all_loggers)
        exportAction.triggered.connect(self.show_exportlogger)
        action_settings = QtGui.QAction('Settings...',self)
        Menu_file.addAction(action_settings)

        Menu_View = self.myQMenuBar.addMenu('&View')
        self.statusap_action = QtGui.QAction('Status Dashboard', self.myQMenuBar, checkable=True)
        self.statusap_action.setChecked(self.FSettings.Settings.get_setting('settings',
        'show_dashboard_info', format=bool))
        self.check_status_ap_dashboard()
        #connect
        self.statusap_action.triggered.connect(self.check_status_ap_dashboard)

        Menu_View.addAction(self.statusap_action)

        #tools Menu
        Menu_tools = self.myQMenuBar.addMenu('&Tools')
        btn_drift = QtGui.QAction('Active DriftNet', self)
        btn_drift.setShortcut('Ctrl+Y')
        btn_drift.triggered.connect(self.show_driftnet)
        btn_drift.setIcon(QtGui.QIcon('icons/capture.png'))
        Menu_tools.addAction(btn_drift)

        #menu module
        Menu_module = self.myQMenuBar.addMenu('&Modules')
        btn_deauth = QtGui.QAction('Wi-Fi deauthentication', self)
        btn_probe = QtGui.QAction('Wi-Fi Probe Request',self)

        # Shortcut modules
        btn_deauth.setShortcut('Ctrl+W')
        btn_probe.setShortcut('Ctrl+K')
        action_settings.setShortcut('Ctrl+X')

        #connect buttons
        btn_probe.triggered.connect(self.showProbe)
        btn_deauth.triggered.connect(self.showDauth)
        action_settings.triggered.connect(self.show_settings)

        #icons modules
        btn_probe.setIcon(QtGui.QIcon('icons/probe.png'))
        btn_deauth.setIcon(QtGui.QIcon('icons/deauth.png'))
        action_settings.setIcon(QtGui.QIcon('icons/setting.png'))

        # add modules menu
        Menu_module.addAction(btn_deauth)
        Menu_module.addAction(btn_probe)

        #menu extra
        Menu_extra= self.myQMenuBar.addMenu('&Help')
        Menu_about = QtGui.QAction('About WiFi-Pickle',self)
        Menu_about.setIcon(QtGui.QIcon('icons/about.png'))
        Menu_about.triggered.connect(self.about)
        Menu_extra.addAction(Menu_about)

        # create box default Form
        self.boxHome = QtGui.QVBoxLayout(self)
        self.boxHome.addWidget(self.myQMenuBar)

        # create Horizontal widgets
        hbox = QtGui.QHBoxLayout()
        self.hBoxbutton.addWidget(self.TabListWidget_Menu)
        self.hBoxbutton.addWidget(self.progress)

        # add button start and stop
        hbox.addLayout(self.hBoxbutton)
        hbox.addWidget(self.Stack)
        self.boxHome.addLayout(hbox)
        self.boxHome.addWidget(self.StatusBar)
        self.TabListWidget_Menu.setCurrentRow(0)
        self.setLayout(self.boxHome)

    def mitmProxy_TAB_Content(self):
        ''' add Layout page MITM Proxy in dashboard '''
        self.MitmProxyTAB = Mitmproxy(self)
        self.ContentTabMitmProxy.addLayout(self.MitmProxyTAB)

    def statusAP_TAB_Content(self):
        ''' add Layout page MITM Proxy in dashboard '''
        self.StatusAPTAB = StatusAccessPoint(self)
        #self.ContentTabStatus.addLayout(self.StatusAPTAB)

    def tcpproxy_TAB_Content(self):
        ''' add Layout page MITM Proxy in dashboard '''
        self.PacketSnifferTAB = PacketsSniffer(self)
        self.ContentTabPackets.addLayout(self.PacketSnifferTAB)

    def imageCapture_TAB_Content(self):
        ''' add Layout page MITM Proxy in dashboard '''
        self.ImageCapTAB = ImageCapture(self)
        self.ContentImageCap.addLayout(self.ImageCapTAB)

    def apMonitor_Tab_Content(self):
        ''' add Layout page Monitor in dashboard '''
        self.PickleMonitorTAB = PickleMonitor(self.FSettings)
        self.ContentTabMonitor.addLayout(self.PickleMonitorTAB)

    def settings_TAB_Content(self):
        ''' add Layout page Pump-settings in dashboard '''
        widgets = {'SettingsAP': self.slipt, 'DockInfo': self.AreaDockInfo,
        'Tab_dock': self.Tab_dock, 'Settings': self.FSettings,'Network': self.GroupAdapter}
        self.PickleSettingsTAB = PickleSettings(None,widgets)
        self.PickleSettingsTAB.checkDockArea.connect(self.get_Content_Tab_Dock)
        self.PickleSettingsTAB.sendMensage.connect(self.set_dhcp_setings_ap)
        self.DHCP = self.PickleSettingsTAB.getPickleSettings()
        self.ContentTabsettings.addLayout(self.PickleSettingsTAB)
        self.deleteObject(widgets)

    def plugins_TAB_Content(self):
        ''' add Layout page Pump-plugins in dashboard '''
        self.ContentTabPlugins.addLayout(self.PopUpPlugins)

    def default_TAB_Content(self):
        ''' configure all widget in home page '''
        self.StatusBar = QtGui.QStatusBar()
        self.StatusBar.setFixedHeight(23)
        self.connectedCount = QtGui.QLabel('')
        self.status_ap_runing = QtGui.QLabel('')
        self.connected_status = QtGui.QLabel('')

        # add widgets in status bar
        self.StatusBar.addWidget(QtGui.QLabel('Connection:'))
        self.StatusBar.addWidget(self.connected_status)
        self.StatusBar.addWidget(QtGui.QLabel('Plugin:'))
        self.StatusBar.addWidget(self.status_plugin_proxy_name)
        self.StatusBar.addWidget(QtGui.QLabel("Status-AP:"))
        self.StatusBar.addWidget(self.status_ap_runing)

        self.set_status_label_AP(False)
        self.progress = ProgressBarWid(total=101)
        self.progress.setFixedHeight(13)
        self.progress.setFixedWidth(140)

        self.StatusBar.addWidget(QtGui.QLabel(''),20)
        self.StatusBar.addWidget(QtGui.QLabel("Clients:"))
        self.connectedCount.setText("0")
        self.connectedCount.setStyleSheet("QLabel {  color : yellow; }")
        self.StatusBar.addWidget(self.connectedCount)
        self.EditApGateway = QtGui.QLineEdit(self)
        self.EditApName = QtGui.QLineEdit(self)
        self.EditApBSSID  = QtGui.QLineEdit(self)
        self.EditApEnableIpTablesRules = QtGui.QCheckBox(self)
        self.EditApFlushIpTablesRules = QtGui.QCheckBox(self)
        self.btn_random_essid = QtGui.QPushButton(self)
        self.EditApChannel = QtGui.QSpinBox(self)
        self.EditApChannel.setMinimum(1)
        self.EditApChannel.setMaximum(13)
        self.EditApChannel.setFixedWidth(50)
        self.EditApGateway.setFixedWidth(120)
        self.EditApGateway.setHidden(True) # disable Gateway
        self.selectCard = QtGui.QComboBox(self)
        self.btn_random_essid.clicked.connect(self.setAP_essid_random)
        self.btn_random_essid.setIcon(QtGui.QIcon('icons/refresh.png'))

        # table information AP connected
        self.TabInfoAP = AutoTableWidget()
        self.TabInfoAP.setRowCount(50)
        self.TabInfoAP.resizeRowsToContents()
        self.TabInfoAP.setSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Preferred)
        self.TabInfoAP.horizontalHeader().setStretchLastSection(True)
        self.TabInfoAP.setSelectionMode(QtGui.QAbstractItemView.NoSelection)
        self.TabInfoAP.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)
        self.TabInfoAP.verticalHeader().setVisible(False)
        self.TabInfoAP.setHorizontalHeaderLabels(list(dict(self.THeaders).keys()))
        self.TabInfoAP.verticalHeader().setDefaultSectionSize(23)
        self.TabInfoAP.horizontalHeader().resizeSection(3,158)
        self.TabInfoAP.horizontalHeader().resizeSection(0,150)
        self.TabInfoAP.horizontalHeader().resizeSection(2,120)
        self.TabInfoAP.horizontalHeader().resizeSection(1,120)
        self.TabInfoAP.setSortingEnabled(True)
        self.TabInfoAP.setObjectName('table_clients')

        #edits
        self.set_initials_configsGUI()
        self.FormGroup2 = QtGui.QFormLayout()
        self.FormGroup3 = QtGui.QGridLayout()

        # popupMenu HTTP server quick start

        # grid network adapter fix
        self.btrn_refresh = QtGui.QPushButton('Refresh')
        self.btrn_refresh.setIcon(QtGui.QIcon('icons/refresh.png'))
        self.btrn_refresh.clicked.connect(self.set_interface_wireless)
        self.btrn_refresh.setFixedWidth(90)
        self.btrn_refresh.setFixedHeight(25)

        self.btrn_find_Inet = QtGui.QPushButton('Check Network Connection')
        self.btrn_find_Inet.setIcon(QtGui.QIcon('icons/router2.png'))
        self.btrn_find_Inet.clicked.connect(self.check_NetworkConnection)
        self.btrn_find_Inet.setFixedHeight(25)
        self.btrn_find_Inet.setFixedWidth(220)

        # group for list network adapters
        self.GroupAdapter = QtGui.QGroupBox()
        self.layoutNetworkAd = QtGui.QHBoxLayout()
        self.GroupAdapter.setTitle('Network Adapter')
        self.layoutNetworkAd.addWidget(self.selectCard)
        self.layoutNetworkAd.addWidget(self.btrn_refresh)
        self.layoutNetworkAd.addWidget(self.btrn_find_Inet)
        self.GroupAdapter.setLayout(self.layoutNetworkAd)

        # settings info access point
        self.GroupAP = QtGui.QGroupBox()
        self.GroupAP.setTitle('Access Point')
        self.FormGroup3.addWidget(QtGui.QLabel("SSID:"), 0, 0)
        self.FormGroup3.addWidget(self.EditApName,0,1)
        self.FormGroup3.addWidget(QtGui.QLabel("BSSID:"), 1, 0)
        self.FormGroup3.addWidget(self.EditApBSSID, 1, 1)
        self.FormGroup3.addWidget(self.btn_random_essid, 1, 2)
        self.FormGroup3.addWidget(QtGui.QLabel("Channel:"), 2, 0)
        self.FormGroup3.addWidget(self.EditApChannel, 2, 1)
        self.FormGroup3.addWidget(QtGui.QLabel("Insert IP Tables Rules at Start"), 3, 0)
        self.FormGroup3.addWidget(self.EditApEnableIpTablesRules, 3, 1)
        self.FormGroup3.addWidget(QtGui.QLabel("Flush IP Tables at Start/Stop"), 4, 0)
        self.FormGroup3.addWidget(self.EditApFlushIpTablesRules, 4, 1)
        self.GroupAP.setLayout(self.FormGroup3)
        self.GroupAP.setFixedWidth(450)

        # create widgets for Wireless Security options
        self.GroupApPassphrase = QtGui.QGroupBox()
        self.GroupApPassphrase.setTitle('Enable Wireless Security')
        self.GroupApPassphrase.setCheckable(True)
        self.GroupApPassphrase.setChecked(self.FSettings.Settings.get_setting('accesspoint','enable_Security',format=bool))
        self.GroupApPassphrase.clicked.connect(self.check_StatusWPA_Security)
        self.layoutNetworkPass  = QtGui.QGridLayout()
        self.editPasswordAP     = QtGui.QLineEdit(self.FSettings.Settings.get_setting('accesspoint','WPA_SharedKey'))
        self.WPAtype_spinbox    = QtGui.QSpinBox()
        self.wpa_pairwiseCB     = QtGui.QComboBox()
        self.lb_type_security   = QtGui.QLabel()
        wpa_algotims = self.FSettings.Settings.get_setting('accesspoint','WPA_Algorithms')
        self.wpa_pairwiseCB.addItems(C.ALGORITMS)
        self.wpa_pairwiseCB.setCurrentIndex(C.ALGORITMS.index(wpa_algotims))
        self.WPAtype_spinbox.setMaximum(2)
        self.WPAtype_spinbox.setMinimum(0)
        self.WPAtype_spinbox.setValue(self.FSettings.Settings.get_setting('accesspoint','WPA_type',format=int))
        self.editPasswordAP.setFixedWidth(150)
        self.editPasswordAP.textChanged.connect(self.update_security_settings)
        self.WPAtype_spinbox.valueChanged.connect(self.update_security_settings)
        self.update_security_settings()

        # add widgets on layout Group
        self.layoutNetworkPass.addWidget(QtGui.QLabel('Security type:'),0,0)
        self.layoutNetworkPass.addWidget(self.WPAtype_spinbox, 0, 1)
        self.layoutNetworkPass.addWidget(self.lb_type_security, 0, 2)
        self.layoutNetworkPass.addWidget(QtGui.QLabel('WPA Algorithms:'), 1, 0)
        self.layoutNetworkPass.addWidget(self.wpa_pairwiseCB, 1, 1)
        self.layoutNetworkPass.addWidget(QtGui.QLabel('Security Key:'), 2, 0)
        self.layoutNetworkPass.addWidget(self.editPasswordAP, 2, 1)
        self.GroupApPassphrase.setLayout(self.layoutNetworkPass)

        self.btn_start_attack = QtGui.QPushButton('Start', self)
        self.btn_start_attack.setIcon(QtGui.QIcon('icons/start.png'))
        self.btn_cancelar = QtGui.QPushButton('Stop', self)
        self.btn_cancelar.setIcon(QtGui.QIcon('icons/Stop.png'))
        self.btn_cancelar.clicked.connect(self.stop_access_point)
        self.btn_start_attack.clicked.connect(self.start_access_point)
        self.btn_cancelar.setEnabled(False)

        self.hBoxbutton =QtGui.QVBoxLayout()
        self.Formbuttons  = QtGui.QFormLayout()
        self.Formbuttons.addRow(self.btn_start_attack,self.btn_cancelar)
        self.hBoxbutton.addLayout(self.Formbuttons)

        self.Main_  = QtGui.QVBoxLayout()
        self.slipt = QtGui.QHBoxLayout()
        self.slipt.addWidget(self.GroupAP)
        self.slipt.addWidget(self.GroupApPassphrase)

        # set main page Tool
        self.widget = QtGui.QWidget()
        self.layout = QtGui.QVBoxLayout(self.widget)
        self.layout.addWidget(self.TabInfoAP)
        self.Main_.addWidget(self.widget)
        self.ContentTabHome.addLayout(self.Main_)

    def show_arp_posion(self):
        ''' call GUI Arp Poison module '''
        if not self.FSettings.Settings.get_setting('accesspoint','statusAP',format=bool):
            self.Farp_posion = GUIModules.frm_Arp_Poison(self.window_phishing)
            self.Farp_posion.setGeometry(0, 0, 450, 300)
            return self.Farp_posion.show()
            QtGui.QMessageBox.information(self,'ARP Poison Attack','this module not work with AP mode enabled. ')
    def show_update(self):
        ''' call GUI software Update '''
        self.FUpdate = self.UpdateSoftware
        self.FUpdate.show()
    def show_exportlogger(self):
        ''' call GUI Report Logger files '''
        self.SessionsAP= loads(str(self.FSettings.Settings.get_setting('accesspoint','sessions')))
        self.FrmLogger =  frm_ReportLogger(self.SessionsAP)
        self.FrmLogger.show()
    def show_settings(self):
        self.FSettings.show()
    def show_windows_update(self):
        ''' call GUI Windows Phishing Page module '''
        self.FWinUpdate = GUIModules.frm_update_attack()
        self.FWinUpdate.setGeometry(QtCore.QRect(100, 100, 300, 300))
        self.FWinUpdate.show()
    def show_dhcpDOS(self):
        ''' call GUI DHCP attack module '''
        self.Fstar = GUIModules.frm_dhcp_Attack()
        self.Fstar.setGeometry(QtCore.QRect(100, 100, 450, 200))
        self.Fstar.show()
    def showProbe(self):
        ''' call GUI Probe Request monitor module '''
        self.Fprobe = GUIModules.frm_PMonitor()
        self.Fprobe.show()
    def showDauth(self):
        ''' call GUI deauth module '''
        self.Fdeauth =GUIModules.frm_deauth()
        self.Fdeauth.setGeometry(QtCore.QRect(100, 100, 200, 200))
        self.Fdeauth.show()
    def show_dns_spoof(self):
        ''' call GUI DnsSpoof module '''
        if  self.FSettings.Settings.get_setting('accesspoint','statusAP',format=bool):
            if self.PopUpPlugins.GroupPluginsProxy.isChecked():
                return QtGui.QMessageBox.information(self,'DnsSpoof with AP','if you want to use the module'
                ' Dns Spoof Attack with AP started, you need to disable Proxy Server. You can change this in plugins tab'
                ' and only it necessary that the option "Enable Proxy Server"  be unmarked and '
                'restart the AP(Access Point).')
        self.Fdns = GUIModules.frm_DnsSpoof(self.window_phishing)
        self.Fdns.setGeometry(QtCore.QRect(100, 100, 450, 500))
        self.Fdns.show()
    def show_PhishingManager(self):
        ''' call GUI phishing attack  '''
        self.FPhishingManager = self.window_phishing
        self.FPhishingManager.txt_redirect.setText('0.0.0.0')
        self.FPhishingManager.show()
    def show_driftnet(self):
        ''' start tool driftnet in Thread '''
        if self.SettingsEnable['ProgCheck'][2]:
            if self.SettingsEnable['ProgCheck'][6]:
                if self.FSettings.Settings.get_setting('accesspoint','statusAP',format=bool):
                    Thread_driftnet = ThreadPopen(['driftnet', '-i',
                    self.SettingsEnable['AP_iface'],'-d','./logs/Tools/Driftnet/',])
                    Thread_driftnet.setObjectName('Tool::Driftnet')
                    self.Apthreads['RougeAP'].append(Thread_driftnet)
                    return Thread_driftnet.start()
                return QtGui.QMessageBox.information(self,'Accesspoint is not running',
                'The access point is not configured, this option require AP is running...')
            return QtGui.QMessageBox.information(self,'xterm','xterm is not installed.')
        return QtGui.QMessageBox.information(self,'driftnet','driftnet is not found.')


    def check_status_ap_dashboard(self):
        ''' show/hide dashboard infor '''
        if self.statusap_action.isChecked():
            self.StatusAPTAB.scroll.setHidden(False)
            return self.FSettings.Settings.set_setting('settings', 'show_dashboard_info', True)
        self.FSettings.Settings.set_setting('settings', 'show_dashboard_info', False)
        self.StatusAPTAB.scroll.setHidden(True)

    def check_StatusWPA_Security(self):
        '''simple connect for get status security wireless click'''
        self.FSettings.Settings.set_setting('accesspoint',
        'enable_security',self.GroupApPassphrase.isChecked())

    def check_NetworkConnection(self):
        ''' update inferfaces '''
        self.btrn_find_Inet.setEnabled(False)
        interfaces = Refactor.get_interfaces()
        self.set_StatusConnected_Iface(False,'checking...',check=True)
        QtCore.QTimer.singleShot(3000, lambda: self.set_backgroud_Network(interfaces))

    def check_plugins_enable(self):
        ''' check plugin options saved in file ctg '''
        if self.FSettings.Settings.get_setting('plugins','tcpproxy_plugin',format=bool):
            self.PopUpPlugins.check_tcpproxy.setChecked(True)
        self.PopUpPlugins.checkBoxTCPproxy()
        if self.FSettings.Settings.get_setting('plugins','responder_plugin',format=bool):
            self.PopUpPlugins.check_responder.setChecked(True)
        if self.FSettings.Settings.get_setting('plugins','meatglue_proxy_plugin',format=bool):
            self.PopUpPlugins.check_meatglue_proxy.setChecked(True)
        if self.FSettings.Settings.get_setting('plugins','mitmproxy_plugin', format=bool):
            self.PopUpPlugins.check_mitmproxy.setChecked(True)
        elif self.FSettings.Settings.get_setting('plugins','mitmproxyssl_plugin', format=bool):
            self.PopUpPlugins.check_mitmproxyssl.setChecked(True)
        elif self.FSettings.Settings.get_setting('plugins','noproxy',format=bool):
            self.PopUpPlugins.check_noproxy.setChecked(True)
            self.PopUpPlugins.GroupPluginsProxy.setChecked(False)
            self.PopUpPlugins.tableplugincheckbox.setEnabled(True)
        self.PopUpPlugins.checkGeneralOptions()

    def check_key_security_invalid(self):
        return QtGui.QMessageBox.warning(self, 'Security Key',
                                   'This Key can not be used.\n'
                                   'The requirements for a valid key are:\n\n'
                                   'WPA:\n'
                                   '- 8 to 63 ASCII characters\n\n'
                                   'WEP:\n'
                                   '- 5/13 ASCII characters or 13/26 hexadecimal characters')

    def check_Wireless_Security(self):
        '''check if user add security password on AP'''
        if self.GroupApPassphrase.isChecked():
            self.confgSecurity = []
            if 1 <= self.WPAtype_spinbox.value() <= 2:
                self.confgSecurity.append('wpa={}\n'.format(str(self.WPAtype_spinbox.value())))
                self.confgSecurity.append('wpa_key_mgmt=WPA-PSK\n')
                self.confgSecurity.append('wpa_passphrase={}\n'.format(self.editPasswordAP.text()))
                if '+' in self.wpa_pairwiseCB.currentText():
                    self.confgSecurity.append('wpa_pairwise=TKIP CCMP\n')
                else:
                    self.confgSecurity.append('wpa_pairwise={}\n'.format(self.wpa_pairwiseCB.currentText()))

            if self.WPAtype_spinbox.value() == 0:
                self.confgSecurity.append('auth_algs=1\n')
                self.confgSecurity.append('wep_default_key=0\n')
                if len(self.editPasswordAP.text()) == 5 or len(self.editPasswordAP.text()) == 13:
                    self.confgSecurity.append('wep_key0="{}"\n'.format(self.editPasswordAP.text()))
                else:
                    self.confgSecurity.append('wep_key0={}\n'.format(self.editPasswordAP.text()))

            for config in self.confgSecurity:
                self.SettingsAP['hostapd'].append(config)
            self.FSettings.Settings.set_setting('accesspoint','WPA_SharedKey',self.editPasswordAP.text())
            self.FSettings.Settings.set_setting('accesspoint','WPA_Algorithms',self.wpa_pairwiseCB.currentText())
            self.FSettings.Settings.set_setting('accesspoint','WPA_type',self.WPAtype_spinbox.value())


    def add_DHCP_Requests_clients(self,mac,user_info):
        ''' get HDCP request data and send for Tab monitor '''
        return self.PickleMonitorTAB.addRequests(mac,user_info,True)

    def add_data_into_QTableWidget(self,client):
        self.TabInfoAP.addNextWidget(client)

    def add_avaliableIterfaces(self,ifaces):
        for index,item in enumerate(ifaces):
            if search('wl', item):
                self.selectCard.addItem(ifaces[index])
        return self.btrn_refresh.setEnabled(True)


    def set_dhcp_setings_ap(self,data):
        ''' get message dhcp configuration '''
        QtGui.QMessageBox.information(self,'settings DHCP',data)

    def set_index_leftMenu(self,i):
        ''' show content tab index TabMenuListWidget '''
        self.Stack.setCurrentIndex(i)

    def set_backgroud_Network(self,get_interfaces):
        ''' check interfaces on background '''
        if get_interfaces['activated'][0] != None:
            self.InternetShareWiFi = True
            self.btrn_find_Inet.setEnabled(True)
            return self.set_StatusConnected_Iface(True, get_interfaces['activated'][0])
        #self.InternetShareWiFi = False
        self.btrn_find_Inet.setEnabled(True)
        return self.set_StatusConnected_Iface(False,'')

    def set_status_label_AP(self,bool):
        if bool:
            self.status_ap_runing.setText("[ON]")
            self.status_ap_runing.setStyleSheet("QLabel {  color : green; }")
        else:
            self.status_ap_runing.setText("[OFF]")
            self.status_ap_runing.setStyleSheet("QLabel {  color : #2e0c47; }")

    def setAP_essid_random(self):
        ''' set random mac 3 last digits  '''
        prefix = []
        for item in [x for x in str(self.EditApBSSID.text()).split(':')]:
            prefix.append(int(item,16))
        self.EditApBSSID.setText(Refactor.randomMacAddress([prefix[0],prefix[1],prefix[2]]).upper())

    def set_proxy_statusbar(self,name,disabled=False):
        if not disabled:
            self.status_plugin_proxy_name.setText('[ {} ]'.format(name))
            self.status_plugin_proxy_name.setStyleSheet("QLabel { background-color: #996633; color : #000000; }")
        else:
            self.status_plugin_proxy_name.setText('[ Disabled ]')
            self.status_plugin_proxy_name.setStyleSheet("QLabel {  background-color: #808080; color : #000000; }")

    def set_StatusConnected_Iface(self,bool,txt='',check=False):
        if bool:
            self.connected_status.setText('[{}]'.format(txt))
            self.connected_status.setStyleSheet("QLabel {  background-color: #996633; color : #000000; }")
        elif bool == False and check == True:
            self.connected_status.setText('[{}]'.format(txt))
            self.connected_status.setStyleSheet("QLabel {  background-color: #808080; color : #000000; }")
        elif bool == False:
            self.connected_status.setText('[None]')
            self.connected_status.setStyleSheet("QLabel {  background-color: #808080; color : #000000; }")

    def set_initials_configsGUI(self):
        ''' settings edits default and check tools '''
        self.get_interfaces = Refactor.get_interfaces()
        self.EditApName.setText(self.FSettings.Settings.get_setting('accesspoint','ssid'))
        self.EditApBSSID.setText(self.FSettings.Settings.get_setting('accesspoint','bssid'))
        self.EditApChannel.setValue(self.FSettings.Settings.get_setting('accesspoint','channel',format=int))
        self.EditApEnableIpTablesRules.setChecked(self.FSettings.Settings.get_setting('accesspoint', 'enableiptables', format = bool))
        self.EditApFlushIpTablesRules.setChecked(self.FSettings.Settings.get_setting('accesspoint', 'flushiptables', format = bool))
        self.SettingsEnable['PortRedirect'] = self.FSettings.redirectport.text()

        # get all Wireless Adapter available and add in comboBox
        interfaces = self.get_interfaces['all']
        wireless = []
        for iface in interfaces:
            if search('wl', iface):
                wireless.append(iface)
        self.selectCard.addItems(wireless)

        if  self.get_interfaces['activated'][0]:
            self.set_StatusConnected_Iface(True,self.get_interfaces['activated'][0])
            self.InternetShareWiFi = True
        else:
            #self.InternetShareWiFi = False
            self.set_StatusConnected_Iface(False,'')

        interface = self.FSettings.Settings.get_setting('accesspoint','interfaceAP')
        if interface != 'None' and interface in self.get_interfaces['all']:
            self.selectCard.setCurrentIndex(wireless.index(interface))

        # check if a program is installed
        lista = [ '', '',popen('which driftnet').read().split('\n')[0],
        popen('which dhcpd').read().split("\n")[0],'',popen('which hostapd').read().split("\n")[0],
        popen('which xterm').read().split("\n")[0]]
        for i in lista:self.SettingsEnable['ProgCheck'].append(path.isfile(i))
        # delete obj
        self.deleteObject(lista)
        self.deleteObject(wireless)

    def set_interface_wireless(self):
        ''' get all wireless interface available '''
        self.selectCard.clear()
        self.btrn_refresh.setEnabled(False)
        ifaces = Refactor.get_interfaces()['all']
        QtCore.QTimer.singleShot(3000, lambda : self.add_avaliableIterfaces(ifaces))
        self.deleteObject(ifaces)

    def set_security_type_text(self,string=str):
        self.lb_type_security.setText(string)
        self.lb_type_security.setFixedWidth(60)
        self.lb_type_security.setStyleSheet("QLabel {border-radius: 2px;"
        "padding-left: 10px; background-color: #3A3939; color : silver; } "
        "QWidget:disabled{ color: #404040;background-color: #302F2F; } ")

    def update_security_settings(self):
        if 1 <= self.WPAtype_spinbox.value() <= 2:
            self.set_security_type_text('WPA')
            if 8 <= len(self.editPasswordAP.text()) <= 63 and is_ascii(str(self.editPasswordAP.text())):
                self.editPasswordAP.setStyleSheet("QLineEdit { border: 1px solid green;}")
            else:
                self.editPasswordAP.setStyleSheet("QLineEdit { border: 1px solid red;}")
            self.wpa_pairwiseCB.setEnabled(True)
            if self.WPAtype_spinbox.value() == 2:
                self.set_security_type_text('WPA2')
        if self.WPAtype_spinbox.value() == 0:
            self.set_security_type_text('WEP')
            if (len(self.editPasswordAP.text()) == 5 or len(self.editPasswordAP.text()) == 13) and \
                    is_ascii(str(self.editPasswordAP.text())) or (len(self.editPasswordAP.text()) == 10 or len(self.editPasswordAP.text()) == 26) and \
                    is_hexadecimal(str(self.editPasswordAP.text())):
                self.editPasswordAP.setStyleSheet("QLineEdit { border: 1px solid green;}")
            else:
                self.editPasswordAP.setStyleSheet("QLineEdit { border: 1px solid red;}")
            self.wpa_pairwiseCB.setEnabled(False)


    def get_Session_ID(self):
        ''' get key id for session AP '''
        session_id = Refactor.generateSessionID()
        while session_id in list(self.SessionsAP.keys()):
            session_id = Refactor.generateSessionID()
        #self.window_phishing.session = session_id
        return session_id

    def get_disable_proxy_status(self,status):
        ''' check if checkbox proxy-server is enable '''
        self.PopUpPlugins.check_noproxy.setChecked(status)
        self.PopUpPlugins.checkGeneralOptions()

    def get_Content_Tab_Dock(self,docklist):
        ''' get tab activated in Advanced mode '''
        self.dockAreaList = docklist

    def get_Error_Injector_tab(self,data):
        ''' get error when ssslstrip or plugin args is not exist '''
        QtGui.QMessageBox.warning(self,'Error Module::Proxy',data)

    def get_status_new_commits(self,flag):
        ''' checks for commits in repository on Github '''
        if flag and self.UpdateSoftware.checkHasCommits:
            reply = QtGui.QMessageBox.question(self, 'Update WiFi-Pickle',
                'would you like to update commits from (github)??', QtGui.QMessageBox.Yes |
                                               QtGui.QMessageBox.No, QtGui.QMessageBox.No)
            if reply == QtGui.QMessageBox.Yes:
                self.UpdateSoftware.show()
        self.Timer.terminate()

    def get_DHCP_Requests_clients(self,data):
        ''' filter: data info sended DHCPD request '''
        self.APclients = {}
        if len(data) == 8:
            device = sub(r'[)|(]',r'',data[5])
            if len(device) == 0: device = 'unknown'
            if Refactor.check_is_mac(data[4]):
                if data[4] not in list(self.TabInfoAP.APclients.keys()):
                    self.APclients[data[4]] = {'IP': data[2],
                    'device': device,'MAC': data[4],'Vendors' : self.get_mac_vendor(data[4])}
                    self.add_DHCP_Requests_clients(data[4],self.APclients[data[4]])
        elif len(data) == 9:
            device = sub(r'[)|(]',r'',data[6])
            if len(device) == 0: device = 'unknown'
            if Refactor.check_is_mac(data[5]):
                if data[5] not in list(self.TabInfoAP.APclients.keys()):
                    self.APclients[data[5]] = {'IP': data[2],
                    'device': device,'MAC': data[5],'Vendors' : self.get_mac_vendor(data[5])}
                    self.add_DHCP_Requests_clients(data[5],self.APclients[data[5]])
        elif len(data) == 7:
            if Refactor.check_is_mac(data[4]):
                print(list(self.TabInfoAP.APclients.keys()))
                if data[4] not in list(self.TabInfoAP.APclients.keys()):
                    leases = IscDhcpLeases(C.DHCPLEASES_PATH)
                    hostname = None
                    try:
                        for item in leases.get():
                            if item.ethernet == data[4]:
                                hostname = item.hostname
                        if hostname == None:
                            item = leases.get_current()
                            hostname = item[data[4]]
                    except:
                        hostname = 'unknown'
                    if hostname == None or len(hostname) == 0:hostname = 'unknown'
                    self.APclients[data[4]] = {'IP': data[2],'device': hostname,
                                               'MAC': data[4], 'Vendors': self.get_mac_vendor(data[4])}
                    self.add_DHCP_Requests_clients(data[4],self.APclients[data[4]])
        if self.APclients != {}:
            self.add_data_into_QTableWidget(self.APclients)
            self.connectedCount.setText(str(len(list(self.TabInfoAP.APclients.keys()))))

    def get_mac_vendor(self,mac):
        ''' discovery mac vendor by mac address '''
        try:
            d_vendor = EUI(mac)
            d_vendor = d_vendor.oui.registration().org
        except:
            d_vendor = 'unknown mac'
        return d_vendor

    def get_DHCP_Discover_clients(self,message):
        '''get infor client connected with AP '''
        self.APclients = {}
        if message['mac_addr'] not in list(self.TabInfoAP.APclients.keys()):
            self.APclients[message['mac_addr']] = \
            {'IP': message['ip_addr'],
            'device': message['host_name'],
             'MAC': message['mac_addr'],
             'Vendors' : self.get_mac_vendor(message['mac_addr'])}

            self.add_DHCP_Requests_clients(message['mac_addr'],self.APclients[message['mac_addr']])
            self.add_data_into_QTableWidget(self.APclients)
            self.connectedCount.setText(str(len(list(self.TabInfoAP.APclients.keys()))))

    def get_Hostapd_Response(self,data):
        ''' get inactivity client from hostapd response'''
        if self.TabInfoAP.APclients != {}:
            if data in list(self.TabInfoAP.APclients.keys()):
                self.PickleMonitorTAB.addRequests(data,self.TabInfoAP.APclients[data],False)
            self.TabInfoAP.delete_item(data)
            self.connectedCount.setText(str(len(list(self.TabInfoAP.APclients.keys()))))

    def get_error_hostapdServices(self,data):
        '''check error hostapd on mount AP '''
        self.stop_access_point()
        return QtGui.QMessageBox.warning(self,'[ERROR] Hostpad',
        'Failed to initiate Access Point, '
        'check output process hostapd.\n\nOutput::\n{}'.format(data))

    def get_soft_dependencies(self):
        ''' check if Hostapd, isc-dhcp-server is installed '''
        self.hostapd_path = self.FSettings.Settings.get_setting('accesspoint','hostapd_path')
        if not path.isfile(self.hostapd_path):
            return QtGui.QMessageBox.information(self,'Error Hostapd','hostapd is not installed')
        if self.FSettings.Settings.get_setting('accesspoint','dhcpd_server',format=bool):
            if not self.SettingsEnable['ProgCheck'][3]:
                return QtGui.QMessageBox.warning(self,'Error dhcpd','isc-dhcp-server (dhcpd) is not installed')
        return True

    def get_meatglue_output(self,data):
        ''' get std_ouput the thread meatGlue and add in DockArea '''
        if self.FSettings.Settings.get_setting('accesspoint','statusAP',format=bool):
            if hasattr(self,'dockAreaList'):
                if self.PickleSettingsTAB.dockInfo['MeatGlueDNSProxy']['active']:
                    try:
                        data = str(data).split(' : ')[1]
                        for line in data.split('\n'):
                            if len(line) > 2 and not self.currentSessionID in line:
                                self.dockAreaList['MeatGlueDNSProxy'].writeModeData(line)
                    except IndexError:
                        return None

    def get_responder_output(self, data):
        ''' get std_ouput the thread responder and add in DockArea '''
        if self.FSettings.Settings.get_setting('accesspoint','statusAP',format=bool):
            if hasattr(self,'dockAreaList'):
                if self.PickleSettingsTAB.dockInfo['Responder']['active']:
                    for line in data.split('\n'):
                        self.dockAreaList['Responder'].writeModeData(line)
                        self.responderlog.info(line)

    def get_dhcpd_output(self, data):
        ''' get std_ouput the thread dhcpd and add in DockArea '''
        if self.FSettings.Settings.get_setting('accesspoint','statusAP',format=bool):
            if hasattr(self,'dockAreaList'):
                if self.PickleSettingsTAB.dockInfo['DHCPD']['active']:
                    try:
                        data = str(data).split(' : ')[1]
                        for line in data.split('\n'):
                            if len(line) > 2:
                                self.dockAreaList['DHCPD'].writeModeData(line)
                    except IndexError:
                        return None

    def get_mitmproxy_output(self, data):
        if self.FSettings.Settings.get_setting('accesspoint','statusAP',format=bool):
            if hasattr(self,'dockAreaList'):
                if self.PickleSettingsTAB.dockInfo['MITMProxy']['active']:
                    try:
                        data = str(data).split(' : ')[1]
                        for line in data.split('\n'):
                            if len(line) > 2:
                                self.dockAreaList['MITMProxy'].writeModeData(line)
                    except IndexError:
                        return None

    def get_TCPproxy_output(self,data):
        ''' get std_output from thread TCPproxy module and add in DockArea'''
        print(str(data))
        if self.FSettings.Settings.get_setting('accesspoint', 'statusAP', format=bool):
            if hasattr(self,'dockAreaList'):
                resultSource = list(dict(data).keys())[0]
                if resultSource == 'urlsCap':
                    if self.PickleSettingsTAB.dockInfo['HTTP-Requests']['active']:
                        self.dockAreaList['HTTP-Requests'].writeModeData(data)
                        self.LogUrlMonitor.info('[ {0[src]} > {0[dst]} ] {1[Method]} {1[Host]}{1[Path]}'.format(
                            data['urlsCap']['IP'], data['urlsCap']['Headers']))
                elif resultSource == 'POSTCreds':
                    if self.PickleSettingsTAB.dockInfo['HTTP-Authentication']['active']:
                        self.dockAreaList['HTTP-Authentication'].writeModeData(data)
                        self.LogCredsMonitor.info('URL: {}'.format(data['POSTCreds']['Url']))
                        self.LogCredsMonitor.info('UserName: {}'.format(data['POSTCreds']['User']))
                        self.LogCredsMonitor.info('UserName: {}'.format(data['POSTCreds']['Pass']))
                        self.LogCredsMonitor.info('Packets: {}'.format(data['POSTCreds']['Destination']))
                elif resultSource == 'image':
                    self.ImageCapTAB.SendImageTableWidgets(data['image'])
                else:
                    self.PacketSnifferTAB.tableLogging.writeModeData(data)
                    self.LogTcpproxy.info('[{}] {}'.format(resultSource,data[resultSource]))


    def deleteObject(self,obj):
        ''' reclaim memory '''
        del obj

    def clean_all_loggers(self):
        ''' delete all logger file in logs/ '''
        content = Refactor.exportHtml()
        resp = QtGui.QMessageBox.question(self, 'About Delete Logger',
            'do you want to delete logs?',QtGui.QMessageBox.Yes |
                                          QtGui.QMessageBox.No, QtGui.QMessageBox.No)
        if resp == QtGui.QMessageBox.Yes:
            del_item_folder(['logs/Caplog/*','logs/ImagesCap/*'])
            for keyFile in content['Files']:
                with open(keyFile,'w') as f:
                    f.write(''),f.close()
            self.FSettings.Settings.set_setting('accesspoint','sessions',dumps({}))
            QtGui.QMessageBox.information(self,'Logger','All Looger::Output has been Removed...')
        self.deleteObject(content)
        self.deleteObject(resp)

    def configure_network_AP(self):
        ''' configure interface and dhcpd for mount Access Point '''
        self.DHCP = self.PickleSettingsTAB.getPickleSettings()
        self.SettingsEnable['PortRedirect'] = self.FSettings.Settings.get_setting('settings','redirect_port')
        self.SettingsAP = {
        'interface':
            [
                'ifconfig %s up'%(self.SettingsEnable['AP_iface']),
                'ifconfig %s %s netmask %s'%(self.SettingsEnable['AP_iface'],self.DHCP['router'],self.DHCP['netmask']),
                'ifconfig %s mtu 1400'%(self.SettingsEnable['AP_iface']),
                'route add -net %s netmask %s gw %s'%(self.DHCP['subnet'],self.DHCP['netmask'],self.DHCP['router'])
            ],
        'kill':
            [
                'iptables --flush',
                'iptables --table nat --flush',
                'iptables --delete-chain',
                'iptables --table nat --delete-chain',
                'ifconfig %s 0'%(self.SettingsEnable['AP_iface']),
                'killall dhpcd 2>/dev/null',
                'ps aux | grep mitmproxy | grep python | awk \'{print $2}\'| xargs kill -9'
            ],
        'hostapd':
            [
                'interface={}\n'.format(str(self.selectCard.currentText())),
                'ssid={}\n'.format(str(self.EditApName.text())),
                'channel={}\n'.format(str(self.EditApChannel.value())),
                'bssid={}\n'.format(str(self.EditApBSSID.text())),
            ]
        }
        print('[*] Enable forwarding in iptables...')
        Refactor.set_ip_forward(1)

        # clean iptables settings
        if self.EditApFlushIpTablesRules.isChecked():
            print("Flushing IP Tables...")
            for line in self.SettingsAP['kill']:
                exec_bash(line)

        # set interface using ifconfig
        if self.EditApEnableIpTablesRules.isChecked():
            print("Configuring IP Tables...")
            for line in self.SettingsAP['interface']:
                exec_bash(line)

    def start_access_point(self):
        ''' start Access Point and settings plugins  '''
        self.saveApSettings()

        if len(self.selectCard.currentText()) == 0:
            return QtGui.QMessageBox.warning(self,'Error interface ','Network interface is not found')
        if not type(self.get_soft_dependencies()) is bool: return

        # check if interface has been support AP mode (necessary for hostapd)
        if self.FSettings.Settings.get_setting('accesspoint','check_support_ap_mode',format=bool):
            if not 'AP' in Refactor.get_supported_interface(self.selectCard.currentText())['Supported']:
                return QtGui.QMessageBox.warning(self,'No Network Supported failed',
                "<strong>failed AP mode: warning interface </strong>, the feature "
                "Access Point Mode is Not Supported By This Device -><strong>({})</strong>.<br><br>"
                "Your adapter does not support for create Access Point Network."
                " ".format(self.selectCard.currentText()))

        # check connection with internet
        self.interfacesLink = Refactor.get_interfaces()

        # check if Wireless interface is being used
        if str(self.selectCard.currentText()) == self.interfacesLink['activated'][0]:
            iwconfig = Popen(['iwconfig'], stdout=PIPE,shell=False,stderr=PIPE)
            for line in iwconfig.stdout.readlines():
                if str(self.selectCard.currentText()) in line:
                    return QtGui.QMessageBox.warning(self,'Wireless interface is busy',
                    'Connection has been detected, this {} is joined the correct Wi-Fi network'
                    ' : Device or resource busy\n{}\nYou may need to another Wi-Fi USB Adapter'
                    ' for create AP or try use with local connetion(Ethernet).'.format(
                    str(self.selectCard.currentText()),line))

        # check if range ip class is same
        gateway_wp, gateway = self.PickleSettingsTAB.getPickleSettings()['router'],self.interfacesLink['gateway']
        if gateway != None:
            if gateway_wp[:len(gateway_wp)-len(gateway_wp.split('.').pop())] == \
                gateway[:len(gateway)-len(gateway.split('.').pop())]:
                return QtGui.QMessageBox.warning(self,'DHCP Server settings',
                    'The <b>DHCP server</b> check if range ip class is same.'
                    'it works, but not share internet connection in some case.<br>'
                    'for fix this, You need change on tab <b> (settings -> Class Ranges)</b>'
                    ' now you have choose the Class range different of your network.')
        del(gateway,gateway_wp)

        # Check the key
        if self.GroupApPassphrase.isChecked():
            if 1 <= self.WPAtype_spinbox.value() <= 2:
                if not (8 <= len(self.editPasswordAP.text()) <= 63 and is_ascii(str(self.editPasswordAP.text()))):
                    return self.check_key_security_invalid()
            if self.WPAtype_spinbox.value() == 0:
                if not (len(self.editPasswordAP.text()) == 5 or len(self.editPasswordAP.text()) == 13) and is_ascii(str(self.editPasswordAP.text()))\
                        and not ((len(self.editPasswordAP.text()) == 10 or len(self.editPasswordAP.text()) == 24) and is_hexadecimal(str(self.editPasswordAP.text()))):
                    return self.check_key_security_invalid()

        print('\n[*] Loading debugging mode')
        # create session ID to logging process
        self.currentSessionID = self.get_Session_ID()
        self.SessionsAP.update({self.currentSessionID : {'started': None,'stoped': None}})
        self.SessionsAP[self.currentSessionID]['started'] = asctime()
        print('[*] Current Session::ID [{}]'.format(self.currentSessionID))

        # clear before session
        if hasattr(self,'dockAreaList'):
            for dock in list(self.dockAreaList.keys()):
                self.dockAreaList[dock].clear()
                self.dockAreaList[dock].stopProcess()
        self.MitmProxyTAB.tableLogging.clearContents()
        self.ImageCapTAB.TableImage.clear()
        self.ImageCapTAB.TableImage.setRowCount(0)

        # check if using ethernet or wireless connection
        print('[*] Configuring hostapd...')
        self.SettingsEnable['AP_iface'] = str(self.selectCard.currentText())
        set_monitor_mode(self.SettingsEnable['AP_iface']).setDisable()
        if self.interfacesLink['activated'][1] == 'ethernet' or self.interfacesLink['activated'][1] == 'ppp' \
                or self.interfacesLink['activated'][0] == None: #allow use without internet connection
            # change Wi-Fi state card
            Refactor.kill_procInterfaceBusy() # killing network process
            try:
                check_output(['nmcli','radio','wifi',"off"]) # old version
            except Exception:
                try:
                    check_output(['nmcli','nm','wifi',"off"]) # new version
                except Exception as error:
                    return QtGui.QMessageBox.warning(self,'Error nmcli',str(error))
            finally:
                call(['rfkill', 'unblock' ,'wifi'])

        #elif self.interfacesLink['activated'][1] == 'wireless':
        #    # exclude USB wireless adapter in file NetworkManager
        #    if not Refactor.settingsNetworkManager(self.SettingsEnable['AP_iface'],Remove=False):
        #        return QMessageBox.warning(self,'Network Manager',
        #        'Not found file NetworkManager.conf in folder /etc/NetworkManager/')

        # get Tab-Hostapd conf and configure hostapd
        self.configure_network_AP()
        self.check_Wireless_Security() # check if user set wireless password
        ignore = ('interface=','ssid=','channel=','essid=')
        with open(C.HOSTAPDCONF_PATH,'w') as apconf:
            for i in self.SettingsAP['hostapd']:apconf.write(i)
            for config in str(self.FSettings.ListHostapd.toPlainText()).split('\n'):
                if not config.startswith('#') and len(config) > 0:
                    if not config.startswith(ignore):
                        apconf.write(config+'\n')
            apconf.close()

        # create thread for hostapd and connect get_Hostapd_Response function
        self.Thread_hostapd = ProcessHostapd({self.hostapd_path:[C.HOSTAPDCONF_PATH]}, self.currentSessionID)
        self.Thread_hostapd.setObjectName('hostapd')
        self.Thread_hostapd.statusAP_connected.connect(self.get_Hostapd_Response)
        self.Thread_hostapd.statusAPError.connect(self.get_error_hostapdServices)
        self.Apthreads['RougeAP'].append(self.Thread_hostapd)

        # disable options when started AP
        self.btn_start_attack.setDisabled(True)
        self.GroupAP.setEnabled(False)
        self.GroupApPassphrase.setEnabled(False)
        self.GroupAdapter.setEnabled(False)
        self.PickleSettingsTAB.GroupDHCP.setEnabled(False)
        self.PopUpPlugins.tableplugins.setEnabled(False)
        self.PopUpPlugins.tableplugincheckbox.setEnabled(False)
        self.btn_cancelar.setEnabled(True)

        # start section time
        self.StatusAPTAB.update_labels()
        self.StatusAPTAB.start_timer()

        # create thread dhcpd and connect fuction get_DHCP_Requests_clients
        if  self.FSettings.Settings.get_setting('accesspoint','dhcpd_server',format=bool):
            print('[*] Configuring dhcpd...')

            # create dhcpd.leases and set permission for acesss DHCPD
            leases = C.DHCPLEASES_PATH
            if not path.exists(leases[:-12]):
                mkdir(leases[:-12])
            if not path.isfile(leases):
                with open(leases, 'wb') as leaconf:
                    leaconf.close()
            uid = getpwnam('root').pw_uid
            gid = getgrnam('root').gr_gid
            chown(leases, uid, gid)

            self.Thread_dhcp = ThRunDhcp(['dhcpd', '--no-pid', '-d', '-f', '-lf', C.DHCPLEASES_PATH, '-cf', 'core/config/dhcpd/dhcpd.conf', self.SettingsEnable['AP_iface']], self.currentSessionID)
            self.Thread_dhcp.sendRequest.connect(self.get_DHCP_Requests_clients)
            self.Thread_dhcp.sendRequest.connect(self.get_dhcpd_output)
            self.Thread_dhcp.setObjectName('ISC DHCPd')
            self.Apthreads['RougeAP'].append(self.Thread_dhcp)
            self.PopUpPlugins.checkGeneralOptions() 
        else:
            print('[*] Skipping DHCP (using external)')

        if self.FSettings.Settings.get_setting('accesspoint','meatglue_dns_proxy',format=bool):
                self.ThreadDNSServer = ProcessThread({'python3.6':['plugins/meatGlue/meatGlueProxy.py','-i',
                str(self.selectCard.currentText()),'-k',self.currentSessionID]})
                self.ThreadDNSServer._ProcssOutput.connect(self.get_meatglue_output)
                self.ThreadDNSServer.setObjectName('MeatGlue DNS Proxy')
                self.Apthreads['RougeAP'].append(self.ThreadDNSServer)
                self.PopUpPlugins.set_MeatGlueProxyRule()

        self.set_status_label_AP(True)
        #self.ProxyPluginsTAB.GroupSettings.setEnabled(False)
        self.FSettings.Settings.set_setting('accesspoint','statusAP',True)
        self.FSettings.Settings.set_setting('accesspoint','interfaceAP',str(self.selectCard.currentText()))

        #create logging for somes threads
        setup_logger('mitmproxy', C.LOG_MITMPROXY, self.currentSessionID)
        setup_logger('urls_capture', C.LOG_URLCAPTURE, self.currentSessionID)
        setup_logger('creds_capture', C.LOG_CREDSCAPTURE, self.currentSessionID)
        setup_logger('tcp_proxy', C.LOG_TCPPROXY, self.currentSessionID)
        setup_logger('responder', C.LOG_RESPONDER, self.currentSessionID)
        self.LogMitmproxy    = getLogger('mitmproxy')
        self.LogUrlMonitor      = getLogger('urls_capture')
        self.LogCredsMonitor    = getLogger('creds_capture')
        self.LogTcpproxy        = getLogger('tcp_proxy')
        self.responderlog       = getLogger('responder')


        if self.PopUpPlugins.check_responder.isChecked():
            # create thread for plugin responder
            self.Thread_responder = ProcessThread({
                'python':[C.RESPONDER_EXEC,'-I', str(self.selectCard.currentText()),'-wrFbv']})
            self.Thread_responder._ProcssOutput.connect(self.get_responder_output)
            self.Thread_responder.setObjectName('Responder')
            self.Apthreads['RougeAP'].append(self.Thread_responder)

        if self.PopUpPlugins.check_mitmproxy.isChecked():
            # Create thread for MITM Proxy
            self.Thread_MitmProxy = ThreadMitmProxy({'bash':['core/helpers/runMitmProxy.sh']})
            self.Thread_MitmProxy._ProcssOutput.connect(self.get_mitmproxy_output)
            self.Thread_MitmProxy.setObjectName('MITM Proxy')
            self.Apthreads['RougeAP'].append(self.Thread_MitmProxy)

        if self.PopUpPlugins.check_mitmproxyssl.isChecked():
            # Create thread for MITM SSL Proxy
            self.Thread_MitmProxy = ThreadMitmProxy({'bash':['core/helpers/runMitmSSLProxy.sh']})
            self.Thread_MitmProxy._ProcssOutput.connect(self.get_mitmproxy_output)
            self.Thread_MitmProxy.setObjectName('MITM Proxy SSL')
            self.Apthreads['RougeAP'].append(self.Thread_MitmProxy)

        # start thread TCPproxy Module
        if self.PopUpPlugins.check_tcpproxy.isChecked():
            if self.PopUpPlugins.check_mitmproxyssl.isChecked():
                self.Thread_TCPproxy = ThreadSniffingPackets(str(self.selectCard.currentText()), [80, 8080, 443], self.currentSessionID)
            else:
                self.Thread_TCPproxy = ThreadSniffingPackets(str(self.selectCard.currentText()), [80, 8080], self.currentSessionID)
            self.Thread_TCPproxy.setObjectName('TCPProxy')
            self.Thread_TCPproxy.output_plugins.connect(self.get_TCPproxy_output)
            self.Apthreads['RougeAP'].append(self.Thread_TCPproxy)

        if self.InternetShareWiFi:
            print('[*] Sharing Internet Connections with NAT...')
        iptables = []
        # get all rules in settings->iptables
        for index in xrange(self.FSettings.ListRules.count()):
           iptables.append(str(self.FSettings.ListRules.item(index).text()))
        for rulesetfilter in iptables:
            #if self.InternetShareWiFi: # disable share internet from network
            if '$inet' in rulesetfilter:
                rulesetfilter = rulesetfilter.replace('$inet',str(self.interfacesLink['activated'][0]))
            if '$wlan' in rulesetfilter:
                rulesetfilter = rulesetfilter.replace('$wlan',str(self.SettingsEnable['AP_iface']))
            # Cheese
            if '$inet' in rulesetfilter or '$wlan' in rulesetfilter:
                continue
            print('Running: {}'.format(rulesetfilter))
            popen(rulesetfilter)

        # start all Thread in sessions
        for thread in self.Apthreads['RougeAP']:
            self.progress.update_bar_simple(20)
            QtCore.QThread.sleep(1)
            thread.start()
        self.progress.setValue(100)
        self.progress.hideProcessbar()
        # check if Advanced mode is enable
        if self.FSettings.Settings.get_setting('dockarea','advanced',format=bool):
            self.PickleSettingsTAB.doCheckAdvanced()

        print('-------------------------------')
        print('AP::[{}] Running...'.format(self.EditApName.text()))
        print('AP::BSSID::[{}] CH {}'.format(Refactor.get_interface_mac(
        self.selectCard.currentText()),self.EditApChannel.value()))
        self.saveApSettings()


    def saveApSettings(self):
        self.FSettings.Settings.set_setting('accesspoint', 'ssid', str(self.EditApName.text()))
        self.FSettings.Settings.set_setting('accesspoint', 'bssid', str(self.EditApBSSID.text()))
        self.FSettings.Settings.set_setting('accesspoint', 'channel', str(self.EditApChannel.value()))
        self.FSettings.Settings.set_setting('accesspoint', 'enableiptables', self.EditApEnableIpTablesRules.isChecked())
        self.FSettings.Settings.set_setting('accesspoint', 'flushiptables', self.EditApFlushIpTablesRules.isChecked())

    def saveApSession(self):
        self.FSettings.Settings.set_setting('accesspoint', 'statusAP', False)
        self.SessionsAP[self.currentSessionID]['stopped'] = asctime()
        self.FSettings.Settings.set_setting('accesspoint', 'sessions', dumps(self.SessionsAP))

    def stop_access_point(self):
        ''' stop all thread :Access point attack and restore all settings  '''
        if self.Apthreads['RougeAP'] == []: return
        print('-------------------------------')
        #self.ProxyPluginsTAB.GroupSettings.setEnabled(True)
        self.saveApSession()
        # check if dockArea activated and stop dock Area
        self.PickleSettingsTAB.GroupArea.setEnabled(True)
        # stop all Thread in create for Access Point
        try:
            for thread in self.Apthreads['RougeAP']:
                thread.stop()
                if hasattr(thread, 'wait'):
                    if not thread.wait(msecs=500):
                        thread.terminate()
        except Exception: pass
        # remove iptables commands and stop dhcpd if pesist in process
        for kill in self.SettingsAP['kill']:
            exec_bash(kill)
        #exec_bash('core/helpers/killMitmProxy.sh')
        # stop time count
        self.StatusAPTAB.stop_timer()
        #disabled options
        # check if persistent option in Settigs is enable
        #if not self.FSettings.Settings.get_setting('accesspoint','persistNetwokManager',format=bool):
        #    Refactor.settingsNetworkManager(self.SettingsEnable['AP_iface'],Remove=True)

        set_monitor_mode(self.SettingsEnable['AP_iface']).setDisable()
        self.set_status_label_AP(False)
        self.progress.setValue(1)
        self.progress.change_color('')
        self.connectedCount.setText('0')
        self.Apthreads['RougeAP'] = []
        self.APclients = {}
        lines = []

        # clear dhcpd.leases
        print('[*] Clearing dhcp leases...')
        system('rm {0} -f'.format(C.DHCPLEASES_PATH))

        self.btn_start_attack.setDisabled(False)
        # disable IP Forwarding in Linux
        Refactor.set_ip_forward(0)
        self.TabInfoAP.clearContents()
        self.TabInfoAP.APclients = {}
        #self.window_phishing.killThread()
        self.PickleMonitorTAB.clearAll()
        self.GroupAP.setEnabled(True)
        self.GroupApPassphrase.setEnabled(True)
        self.GroupAdapter.setEnabled(True)
        self.PickleSettingsTAB.GroupDHCP.setEnabled(True)
        self.PopUpPlugins.tableplugins.setEnabled(True)
        self.PopUpPlugins.tableplugincheckbox.setEnabled(True)
        self.btn_cancelar.setEnabled(False)
        self.progress.showProcessBar()
        print('[*] Stopped')

    def about(self):
        ''' open about GUI interface '''
        self.Fabout = frmAbout(author,emails,
        version,update,license,desc)
        self.Fabout.show()
    def issue(self):
        ''' open issue in github page the project '''
        url = QtCore.QUrl('https://github.com/P0cL4bs/WiFi-Pickle/issues/new')
        if not QtGui.QDesktopServices.openUrl(url):
            QtGui.QMessageBox.warning(self, 'Open Url', 'Could not open url: {}'.format(url))
