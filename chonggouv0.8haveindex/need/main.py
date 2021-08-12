# -*- coding: utf-8 -*-
import logging
from pandas.core.frame import DataFrame
LOG_FORMAT = "%(asctime)s>%(levelname)s>PID:%(process)d %(thread)d>%(module)s>%(funcName)s>%(lineno)d>%(message)s"
logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT, )

#删除print调试
# def print(*args, **kwargs):
#     pass

# 是否打印调试信息标志
debug = True
if debug==True:
    logging.debug("进入主程序，开始导入包...")

import time
from time import sleep
import os
import sys
import re
import codecs
import threading
import binascii

from PyQt5 import QtCore
from PyQt5.QtGui import QIntValidator
from PyQt5.QtCore import QTranslator
from PyQt5.QtWidgets import QDialog,QMainWindow,QMessageBox,QComboBox,QLabel,QActionGroup
from PyQt5.QtWidgets import QFileDialog,QListWidgetItem,QHeaderView,QTableWidgetItem,QScrollArea,QVBoxLayout
from PyQt5 import QtCore, QtGui, QtWidgets, QtWebEngineWidgets
from PyQt5.QtWebEngineWidgets import QWebEngineSettings

from need.chuankou import Ui_MainWindow
import serial
from need.userSerial import userSerial,suportBandRateList

from need import utils
import csv
import json
#加载dataFrame表格
import pandas as pd
#加入mainks.py
from need.mainks import Mywin
# 配置
# 统计线程周期
periodStatistics = 2
# 错误替换字符
replaceError = "*E*"
def userCodecsReplaceError(error):
    """
    字符编解码异常处理 直接将错误字节替代为"*E*"
    :param error: UnicodeDecodeError实例
    :return:
    """
    if not isinstance(error, UnicodeDecodeError):
        raise error

    return (replaceError, error.start + 1)

def userCodecsError(error):
    """
    字符编解码异常处理 暂缓+替代
    Error handler for surrogate escape decoding.

    Should be used with an ASCII-compatible encoding (e.g., 'latin-1' or 'utf-8').
    Replaces any invalid byte sequences with surrogate code points.

    """
    if not isinstance(error, UnicodeDecodeError):
        raise error
    if error.end - error.start <= 3:
        raise error
    # 从出错位置开始到所处理数据结束，如果数据长度>=5,则第一个字节必然是错误字节，而非未完整接收
    # 此时直接将第一个字节使用*E*代替，并返回下一个字节索引号
    else:
        return (replaceError, error.start + 1)

# 添加自定义解码异常处理handler
codecs.register_error("userCodecsReplaceError",userCodecsReplaceError)
codecs.register_error("userCodecsError",userCodecsError)

#主界面
class userMain(QMainWindow,Ui_MainWindow):
    #自定义信号用来发送底层的dict数据给子绘图窗口数据
    dictsignal = QtCore.pyqtSignal(dict)

    #自定义信号和槽来显示接收数据
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        if debug == True:
            logging.debug("初始化主程序:")



        # 实例化翻译家
        self.trans = QTranslator()
        self.setWindowTitle('测试平台遥测工具')

        # # 初始化queue
        # self.queue_recv = Queue(maxsize=240)

        # 初始化串口对象
        self.comBoxPortBuf = ""#当前使用的串口号
        self.comPortList = [] #系统可用串口号
        self.com = userSerial(baudrate=115200, timeout=0)#实例化串口对象,这里不就打开了？

        # 自定义信号2个，一个是收到数据，一个是收到错误数据
        self.com.signalRcv.connect(self.on_com_signalRcv) #当接收到信号
        self.com.signalRcvError.connect(self.on_com_signalRcvError) #当接收到错误数据信号连接
        self.com.signalRcvdata.connect(self.on_com_signalRcvdata) #当解析变成dict后发送到UI

        #初始化端口组合list和波特率list
        self.update_comboBoxPortList()#更新系统支持的串口设备并更新端口组合框内容
        self.update_comboBoxBandRateList()# 更新波特率组合框内容

        #子窗口状态变量
        self.zichuankou = 0 #0代表未打开，1代表已打开

        #初始化默认界面
        #~~~~~~~~
        self.save_dict = {} #串口接收进来的数据字典
        #~~~~~~~~
        self.rcvAsciiBuf = bytearray() # 接收缓冲 用于字符接收模式时解决一个字符的字节码被分两批接收导致的解码失败问题
        self.rcvTotal = 0 #初始化接收数据总和
        self.rcvTotalLast = 0 #初始化结束最后一次的数据量
        #~~~~~~~~
        self.sndTotal = 0
        self.sndTotalLast = 0

        self.sndAsciiHex = True#发送ASCII模式
        self.radioButtonTxAscii.setChecked(True) #发送模式初始化为ASCII模式
        self.radioButtonStop1Bit.setChecked(True)
        self.radioButtonParityOdd.setChecked(True)
        self.radioButtonData8Bit.setChecked(True)

        self.sndAutoCLRF = False #发送追加换行
        self.txPeriodEnable = False #周期发送使能

        self.lineEditPeriodMs.setValidator(QIntValidator(0,99999999))# 周期发送时间间隔验证器
        self.txPeriod = int(self.lineEditPeriodMs.text())#周期长度ms

        self.textEditSendLastHex = self.textEditSend.toPlainText()#Hex模式时 发送编辑区上次Hex字符串备份，用于使用re验证输入有效性
        self.periodSendBuf = bytearray()#周期发送时 发送数据缓存

        # 获取状态栏对象
        self.user_statusbar = self.statusBar()
        
        # 在状态栏增加接收总数 接收速率 发送总数 发送速率的标签
        _translate = QtCore.QCoreApplication.translate
        self.NullLabel = QLabel("")
        self.rcvTotalLabel = QLabel(_translate("MainWindow", "接收总和:"))
        self.rcvTotalValueLabel = QLabel()
        self.rcvSpeedLabel = QLabel(_translate("MainWindow", "接收速率:"))
        self.rcvSpeedValueLabel = QLabel()
        self.sndTotalLabel = QLabel(_translate("MainWindow", "发送总和:"))
        self.sndTotalValueLabel = QLabel()
        self.sndSpeedLabel = QLabel(_translate("MainWindow", "发送速率:"))
        self.sndSpeedValueLabel = QLabel()

        # 右下角窗口尺寸调整符号
        self.user_statusbar.setSizeGripEnabled(False)
        self.user_statusbar.setStyleSheet("QStatusBar.item{border:10px}")
        # 非永久信息 一般信息显示，在最左边，通过addWIdget insertWidget插入
        # 通过此方法添加必要时会被更改和覆盖
        inter = 5
        self.user_statusbar.addWidget(self.NullLabel, inter)
        self.user_statusbar.addWidget(self.rcvTotalLabel, inter)
        self.user_statusbar.addWidget(self.rcvTotalValueLabel, inter)
        self.user_statusbar.addWidget(self.rcvSpeedLabel, inter)
        self.user_statusbar.addWidget(self.rcvSpeedValueLabel, inter)
        self.user_statusbar.addWidget(self.sndTotalLabel, inter)
        self.user_statusbar.addWidget(self.sndTotalValueLabel, inter)
        self.user_statusbar.addWidget(self.sndSpeedLabel, inter)
        self.user_statusbar.addWidget(self.sndSpeedValueLabel, inter)



        if debug == True:
            logging.debug("当前系统可用端口:{}".format(self.comPortList))
            
        #~~~~~~~~~~~变量参数初始化~~~~~~~~
        self.user_para_addr = [] #初始化用户选择的数据变量地址信息'0c67AE6A'4字节列表
        self.user_para_dict = {} #初始化用户选择的数据变量地址信息以及其变量名
        self.user_send_length = 0 #用户选择的参数数量
        self.user_send_message = '' #用int数组展示
        self.mapDict = {}

        #~~~~~~~~~~~加载用户变量表格~~~~~~~~~~~~~
        if debug==True:
            logging.debug("开始导入变量中文名、变量类型参数......")
        self.df = pd.read_csv(os.path.abspath('varstatic.csv'),encoding='gbk')

        if debug==True:
            print('导入的变量表格为：\r',self.df)
        if debug==True:
            logging.debug("导入变量中文名、变量类型参数成功")
            logging.debug("初始化主程序完成")
            

        #~~~~~~~~~~~按钮UI界面连接函数~~~~~~~~~~~~
        self.pushButton_map.clicked.connect(self.mapparser_cb) #点击选中文件，得到文件路径存到全类变量self.map_file_name
        self.pushButton_create.clicked.connect(self.map_create_cb) #点击生成参数列表
        self.pushButton_del.clicked.connect(self.list_remove_item) #点击按钮删除选中项
        self.pushButton_cle.clicked.connect(self.list_clear_cb) #点击清空列表
        self.pushButton_order.clicked.connect(self.create_order) #生成获取参数的指令
        self.pushButton_raise.clicked.connect(self.create_order_send) #发送生产的指令
        self.pushButtonSave.clicked.connect(self.save_file_thread) #点击启动保存数据线程
        self.pushButtonSaveCancel.clicked.connect(self.save_file_cancel) #点击停止保存文件
        self.pushButton_bin.clicked.connect(self.bin_file_cb) #点击选中文件获得全类变量绝对路径self.map_file_name
        self.pushButton_send_bin.clicked.connect(self.send_bin_cb) #点击发送bin文件
        self.bin_send_thread = Send_bin_Thread(self) #创建发送bin文件线程
        self.bin_send_thread.sin_out.connect(self.text_display) #把发送bin文件的消息传给text_display函数
        self.pushButton.clicked.connect(self.show_echarts) #点击展示echarts图像
        self.pushButton_2.clicked.connect(self.choosecsv) #选择csv文件

        #~~~~~~~~~~生产Table1~用来展示变量值~~~~~~~~~
        self.table1.setColumnCount(2)#信息列数固定为2
        self.table1.setHorizontalHeaderLabels(["变量名","数值"])
        #最后一列自动拉伸
        self.table1.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        QHeaderView.Stretch #自适应宽度
        self.table1.setRowCount(15) #后面需要根据用户选择数量进行更变，在生产指令的时候

        #下面函数用于第三个tab页面
        self.loadweb()


#~~~~~~~~~~~~~~~~~~~~初始化直接运行的函数（也就是起始运行一次）~~~~~~~~~~~~~~~~~~~~~~~~~~
#     加载web界面
    def loadweb(self):
        webSettings = QWebEngineSettings.globalSettings()
        webSettings.setAttribute(QWebEngineSettings.JavascriptEnabled,True)
        webSettings.setAttribute(QWebEngineSettings.PluginsEnabled,True)
        webSettings.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows,True)
        
        self.webView2 = QtWebEngineWidgets.QWebEngineView()
        self.webView2.load(QtCore.QUrl(QtCore.QFileInfo("./showdatas.html").absoluteFilePath()))
        self.hLayout_2.addWidget(self.webView2)

#     更新系统支持的串口设备并更新端口组合框内容
    def update_comboBoxPortList(self):
        start = time.time()
        # 获取可用串口号列表
        newportlistbuf = userSerial.getPortsList()
        if self.comBoxPortBuf == "" or  newportlistbuf != self.comPortList:
            self.comPortList = newportlistbuf

            if len(self.comPortList) > 0:
                # 将串口号列表更新到组合框
                self.comboBoxPort.setEnabled(False)
                self.comboBoxPort.clear()
                self.comboBoxPort.addItems([self.comPortList[i][1] for i in range(len(self.comPortList))])

                # self.comBoxPortBuf为空值 默认设置为第一个串口
                if self.comBoxPortBuf == "":
                    self.comBoxPortBuf = self.comPortList[0][1]
                else:
                    # 遍历当前列表 查找是否上次选定的串口在列表中出现，如果出现则选中上次选定的串口
                    seq = 0
                    for i in self.comPortList:
                        if i[1] == self.comBoxPortBuf:
                            self.comboBoxPort.setCurrentIndex(seq)
                            break
                        seq+=1
                    # 全部遍历后发现上次选定串口无效时，设置第一个串口
                    else:
                        self.comBoxPortBuf = self.comPortList[0][1]

                self.comboBoxPort.setEnabled(True)
                if debug == True:
                    logging.debug("更新可用串口列表")
            else:
                self.comboBoxPort.setEnabled(False)
                self.comboBoxPort.clear()
                self.comBoxPortBuf = ""

                _translate = QtCore.QCoreApplication.translate
                self.comboBoxPort.addItem(_translate("MainWindow", "没有可用的端口"))
                # self.comboBoxPort.setEnabled(True)
                if debug == True:
                    logging.warning("更新可用串口列表：无可用串口设备")
        else:
            if debug == True:
                logging.debug("更新可用串口列表：列表未发生变化")

        stop = time.time()
        if debug == True:
            logging.debug("更新串口列表时间{}s".format(stop-start))

    #波特率___初始化时候需要执行一次的波特率放入界面
    def update_comboBoxBandRateList(self):
        # 将串口号列表更新
        self.comboBoxBand.setEnabled(False)
        self.comboBoxBand.clear()
        self.comboBoxBand.addItems([str(i) for i in suportBandRateList])
        # 设置默认波特率
        self.comboBoxBand.setCurrentText("115200")
        # print(self.comboBoxBand.currentIndex())
        self.comboBoxBand.setEnabled(True)


#~~~~~~~~~~~~~~~~~~~~~~~~~pyqt界面触发信号槽~~~~~~~~~~~~~~~~~~~~~~~~~~
    #改变串口号时候__当用户选择点下拉框触发这个信号槽
    @QtCore.pyqtSlot(str)
    def on_comboBoxPort_activated(self, text):# 手动触发时启动
        if isinstance(text,int):
            if debug == True:
                logging.debug("更换选中串口号:{}".format(text))
        if isinstance(text,str):
            if debug == True:
                logging.debug("更换选中串口名称:{}".format(text))
            if(text != ""):
                # 切换串口前，如果当前为已打开端口则关闭端口
                if self.com.getPortState() == True:
                    self.on_pushButtonOpen_toggled(False)
                self.comBoxPortBuf = text

    #改变波特率时候__当用户选择不同波特率
    @QtCore.pyqtSlot(str)
    def on_comboBoxBand_activated(self, text):
        if isinstance(text,str):
            try:
                self.com.port.baudrate = (int(text))
                if debug == True:
                    logging.debug("更新波特率:{}".format(self.com.port.baudrate))
            except Exception as e:
                if debug == True:
                    logging.error("更新波特率:{}".format(e))

    # # 数据位
    def update_radioButtonDataBit(self,bit,checked):
        if checked == True:
            try:
                self.com.port.bytesize = bit
                if debug == True:
                    logging.debug("更新数据位:{}".format(self.com.port.bytesize))
            except Exception as e:
                if debug == True:
                    logging.error("更新数据位:{}".format(e))
        else:
            try:
                if debug == True:
                    logging.debug("取消此数据位:{}".format(self.com.port.bytesize))
            except Exception as e:
                if debug == True:
                    logging.error("取消此数据位:{}".format(e))

    @QtCore.pyqtSlot(bool)
    def on_radioButtonData8Bit_toggled(self,checked):
        self.update_radioButtonDataBit(serial.EIGHTBITS, checked)
    @QtCore.pyqtSlot(bool)
    def on_radioButtonData7Bit_toggled(self,checked):
        self.update_radioButtonDataBit(serial.SEVENBITS, checked)
    @QtCore.pyqtSlot(bool)
    def on_radioButtonData6Bit_toggled(self,checked):
        self.update_radioButtonDataBit(serial.SIXBITS, checked)
    @QtCore.pyqtSlot(bool)
    def on_radioButtonData5Bit_toggled(self,checked):
        self.update_radioButtonDataBit(serial.FIVEBITS,checked)

    # # 校验位
    def update_radioButtonParity(self,parity,checked):
        if checked == True:
            try:
                self.com.port.parity = parity
                if debug == True:
                    logging.debug("更新校验:{}".format(self.com.port.parity))
            except Exception as e:
                if debug == True:
                    logging.error("更新校验:{}".format(e))
        else:
            try:
                if debug == True:
                    logging.debug("取消此校验:{}".format(self.com.port.parity))
            except Exception as e:
                if debug == True:
                    logging.error("取消此校验:{}".format(e))

    @QtCore.pyqtSlot(bool)
    def on_radioButtonParityNone_toggled(self,checked):
        self.update_radioButtonParity(serial.PARITY_NONE,checked)
    @QtCore.pyqtSlot(bool)
    def on_radioButtonParityEven_toggled(self,checked):
        self.update_radioButtonParity(serial.PARITY_EVEN,checked)
    @QtCore.pyqtSlot(bool)
    def on_radioButtonParityOdd_toggled(self,checked):
        self.update_radioButtonParity(serial.PARITY_ODD,checked)
    @QtCore.pyqtSlot(bool)
    def on_radioButtonParityMark_toggled(self,checked):
        self.update_radioButtonParity(serial.PARITY_MARK,checked)
    @QtCore.pyqtSlot(bool)
    def on_radioButtonSpace_toggled(self,checked):
        self.update_radioButtonParity(serial.PARITY_SPACE,checked)

    # # 流控
    @QtCore.pyqtSlot(bool)
    def on_checkBoxFlowCtrl_toggled(self,checked):
        try:
            self.com.port.rtscts = checked
            if debug == True:
                logging.debug("更新流控开关:{}".format(self.com.port.rtscts))
        except Exception as e:
            if debug == True:
                logging.error("更新流控开关失败:{}".format(e))

    # # 停止位
    def update_radioButtonStop(self,stop,checked):
        if checked == True:
            try:
                self.com.port.stopbits = stop
                if debug == True:
                    logging.debug("更新停止位:{}".format(self.com.port.stopbits))
            except Exception as e:
                if debug == True:
                    logging.error("更新停止位:{}".format(e))
        else:
            try:
                if debug == True:
                    logging.debug("取消此停止位:{}".format(self.com.port.stopbits))
            except Exception as e:
                if debug == True:
                    logging.error("取消此停止位:{}".format(e))

    @QtCore.pyqtSlot(bool)
    def on_radioButtonStop1Bit_toggled(self,checked):
        self.update_radioButtonStop(serial.STOPBITS_ONE, checked)
    @QtCore.pyqtSlot(bool)
    def on_radioButtonStop2Bit_toggled(self,checked):
        self.update_radioButtonStop(serial.STOPBITS_TWO, checked)
    @QtCore.pyqtSlot(bool)
    def on_radioButtonStop1_5Bit_toggled(self,checked):
        self.update_radioButtonStop(serial.STOPBITS_ONE_POINT_FIVE, checked)

    # # 打开/关闭开关
    @QtCore.pyqtSlot(bool)
    def on_pushButtonOpen_toggled(self,checked):
        print('点击了打开按钮~~~~~~')
        if debug == True:
            logging.debug("打开按钮:Toggle{}".format(checked))
        if checked ==True:
        #  打开指定串口
            portBuf = ""
            # 在端口列表中搜索当前串口名称对应的端口号
            seq = 0
            for i in self.comPortList:
                if i[1] == self.comBoxPortBuf:
                    portBuf  = i[0]
                    break
                seq+=1
            if (portBuf != ""):
                try:
                    self.com.open(portBuf)
                    if debug == True:
                        logging.debug("端口{}已打开".format(portBuf))

                    _translate = QtCore.QCoreApplication.translate
                    self.pushButtonOpen.setText(_translate("MainWindow","关闭串口"))

                    # 在userSerial类中已经实现了接收完成signalRcv信号机制，无需启动线程刷屏，只需将信号关联到对应的槽函数即可
                    # # 开启接收线程刷屏
                    # threading.Thread(target=self.__textBrowserReceiveRefresh, args=(), daemon=True).start()
                    # 开启统计线程
                    threading.Thread(target=self.periodUpdateStatistics, args=(), daemon=True).start()

                except Exception as e:
                    self.NullLabel.setText(e.args[0].args[0])
                    if debug == True:
                        logging.error("端口{}打开出错".format(e))

            else:
                if debug == True:
                    logging.debug("无可用串口")
                self.pushButtonOpen_State_Reset()
        else:
        #  关闭当前打开的串口
            if self.com.getPortState() == True:
                self.com.port.close()
                if debug == True:
                    logging.debug("端口{}已关闭".format(self.comBoxPortBuf))
            else:
                if debug == True:
                    logging.debug("端口{}未打开".format(self.comBoxPortBuf))
            self.pushButtonOpen_State_Reset()

    def pushButtonOpen_State_Reset(self):
        _translate = QtCore.QCoreApplication.translate
        self.pushButtonOpen.setText(_translate("MainWindow", "打开串口"))
        # 设置Checked状态会导致on_pushButtonOpen_toggled触发
        self.pushButtonOpen.setChecked(False)

    # 串口设备更新按键
    @QtCore.pyqtSlot()
    def on_pushButtonUpdate_pressed(self):
        if debug == True:
            logging.debug("更新串口设备开始")
        self.update_comboBoxPortList()
        if debug == True:
            logging.debug("更新串口设备结束")

#发送区设置~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# 串口发送设置
#     # ASCII发送
#     self.radioButtonTxAscii
    @QtCore.pyqtSlot(bool)
    def on_radioButtonTxAscii_toggled(self,checked):
        if checked == True:
            self.sndAsciiHex = True
            # 设置自动换行使能
            self.checkBoxTxAutoCRLF.setEnabled(True)
            if debug == True:
                logging.debug("更新发送模式:ASCII")
        else:
            if debug == True:
                logging.debug("取消发送模式:ASCII")
#     # ASCII发送时自动追加回车换行
#     self.checkBoxTxAutoCRLF
    @QtCore.pyqtSlot(bool)
    def on_checkBoxTxAutoCRLF_toggled(self,checked):
        self.sndAutoCLRF = checked
        if debug == True:
            logging.debug("更新发送自动换行:{}".format(checked))
#     # Hex发送
#     self.radioButtonTxHex
    @QtCore.pyqtSlot(bool)
    def on_radioButtonTxHex_toggled(self,checked):
        if checked == True:
            self.sndAsciiHex = False
            # 设置自动换行禁能
            self.checkBoxTxAutoCRLF.setEnabled(not checked)
            if debug == True:
                logging.debug("更新发送模式:Hex")
        else:
            if debug == True:
                logging.debug("取消发送模式:Hex")
#     # 周期发送使能
#     self.checkBoxTxPeriodEnable
    @QtCore.pyqtSlot(bool)
    def on_checkBoxTxPeriodEnable_toggled(self,checked):
        self.txPeriodEnable = checked
        if debug == True:
            logging.debug("更新周期发送使能:{}".format(checked))
#     # 发送周期
#     self.lineEditPeriodMs
    @QtCore.pyqtSlot(str)
    def on_lineEditPeriodMs_textChanged(self,text):
        if (text != "" and text != "0"):#
            # 当text是0时，lstrip("0")将导致字符串结果是""
            self.lineEditPeriodMs.setText((self.lineEditPeriodMs.text().lstrip('0')))
            self.txPeriod = int(text)
        else:#空或者0
            self.lineEditPeriodMs.setText("0")
            self.txPeriod = 0
        if debug == True:
            logging.debug("更新周期发送时间设置:text-->{}  period-->{}".format(text, self.txPeriod))

    @QtCore.pyqtSlot(str)
    def on_com_signalRcvError(self,txt):
        if debug == True:
            logging.error("串口异常关闭:{}".format(txt))
        self.on_pushButtonOpen_toggled(False)
        # 更新串口列表
        self.update_comboBoxPortList()
        pass

#发送编辑区~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    @QtCore.pyqtSlot()
    def on_textEditSend_textChanged(self):
        # 如果是Hex发送模式 使用正则过滤输入信息
        if self.sndAsciiHex == False:
            currHex = self.textEditSend.toPlainText()
            # 对比当前内容与上次内容差别
            if self.textEditSendLastHex != currHex:
                # 匹配所有16进制字符和空格
                patt = r"[0-9a-fA-F ]+"
                pattern = re.compile(patt)
                reObj = pattern.match(currHex)

                if reObj != None:
                    self.textEditSendLastHex = reObj.group()
                    self.textEditSend.setText(self.textEditSendLastHex)
                    self.textEditSend.moveCursor(self.textEditSend.textCursor().End)
                else:# 无效输入 清除输入区
                    # 必须先清除上次内容记录，然后调用self.textEditSend.clear()
                    # 因为调用此方法立即导致再次进入on_textEditSend_textChanged槽函数执行操作，
                    # 如果未清除上次内容记录，对比后再次发现两次内容差别，执行模式匹配后，再次清除输入区，最后会产生无限循环
                    self.textEditSendLastHex = ""
                    self.textEditSend.clear()
        # 字符串发送模式不限制数据
        else:
            pass

#     发送历史区
    @QtCore.pyqtSlot(str)
    def on_comboBoxSndHistory_activated(self, text):
        if isinstance(text,str):
            self.textEditSend.setText(text)
            self.textEditSend.moveCursor(self.textEditSend.textCursor().End)

#     # 发送按钮
#     self.pushButtonSend
    @QtCore.pyqtSlot(bool)
    def on_pushButtonSend_toggled(self,checked):
        if debug == True:
            logging.debug("发送按钮点击了:Toggle{}".format(checked))
        if checked == True:
            # 判断串口状态
            if self.com.getPortState() == True:
        #       查询发送区中是否有可用数据
                txt = self.textEditSend.toPlainText()
                if txt != "":
                    if debug == True:
                        logging.debug("原始发送数据:{}".format(txt))

                    # 添加到发送历史
                    self.comboBoxSndHistory.insertItem(0,txt)
                    self.comboBoxSndHistory.setCurrentIndex(0)
        #       判断当前发送模式时
                    if self.sndAsciiHex == True:  # 发送ASCII模式
                        # 发送追加换行
                        if self.sndAutoCLRF == True:
                            txt+="\r\n"

                        buf = txt.encode("utf-8")
                        if debug == True:
                            logging.debug("utf-8编码字节数组:{}".format(buf))

                        # 判断周期发送
                        if self.txPeriodEnable == True:  # 周期发送使能
                            self.periodSendBuf = buf
                            _translate = QtCore.QCoreApplication.translate
                            self.pushButtonSend.setText(_translate("MainWindow", "停止串口"))
                            threading.Thread(target=self.periodSendThread, args=(), daemon=True).start()

                        else:
                        # 单次发送  端口已被打开时开始发送
                            self.com.send(buf)
                            self.sndTotal+=len(buf)
                            self.pushButtonSend_State_Reset()
                    else:
                        # Hex模式发送
                        try:
                            buf = bytes.fromhex(txt)
                            if debug == True:
                                logging.debug("16进制数据:{}".format(buf))

                            # 判断周期发送
                            if self.txPeriodEnable == True:  # 周期发送使能
                                self.periodSendBuf = buf
                                _translate = QtCore.QCoreApplication.translate
                                self.pushButtonSend.setText(_translate("MainWindow", "点击停止"))
                                threading.Thread(target=self.periodSendThread, args=(), daemon=True).start()
                            else:
                                # 单次发送  端口已被打开时开始发送
                                self.com.send(buf)
                                self.sndTotal += len(buf)
                                self.pushButtonSend_State_Reset()
                        except Exception as e:
                            self.pushButtonSend_State_Reset()
                            if debug == True:
                                logging.error("串口发送16进制转换失败:{}".format(e))
                            # 使用re模块从args中筛选出错误位置
                            patt = r"position (\d+)$"
                            patton = re.compile(patt)
                            reObj = patton.search(e.args[0])
                            # print("\treObj:{}".format(reObj))
                            if (reObj != None):
                                if reObj.lastindex > 0:
                                    errIndex = int(reObj.group(1))
                                    if debug == True:
                                        logging.error("\t出错位置:{}".format(errIndex))
                                    # 提示当前输入数据不符合Hex字符串格式要求
                                    reply = QMessageBox.question(self,'Hex字符串格式异常','第{}个字符不符合Hex字符串格式要求,请重新输入'.format(errIndex))
                else:
                    if debug == True:
                        logging.warning("发送区无有效数据")
                    self.pushButtonSend_State_Reset()
            else:
                if debug == True:
                    logging.debug("串口未打开")
                self.pushButtonSend_State_Reset()
        else:
            self.pushButtonSend_State_Reset()
    #被函数连接的刷新发送按钮函数
    def pushButtonSend_State_Reset(self):
        _translate = QtCore.QCoreApplication.translate
        self.pushButtonSend.setText(_translate("MainWindow", "发送"))
        self.pushButtonSend.setChecked(False)
    #上面发送按钮连接的函数启动了下面函数线程
    def periodSendThread(self):
        start =0
        stop =  0
        if self.periodSendBuf != None:
            if debug == True:
                logging.debug("周期发送线程开启")

            while self.txPeriodEnable and self.pushButtonSend.isChecked()==True and self.com.getPortState() == True:
                self.com.send(self.periodSendBuf)
                self.sndTotal += len(self.periodSendBuf)
                if debug == True:
                    logging.debug("周期发送:{}".format(self.periodSendBuf))
                if self.txPeriod > 0:
                    sleep(self.txPeriod/1000)
            if debug == True:
                logging.debug("周期发送发送")

    #该函数用来更新status中数据
    def periodUpdateStatistics(self):
        while self.com.getPortState() == True:
            sndSpeed = (self.sndTotal-self.sndTotalLast)//periodStatistics
            rcvSpeed = (self.rcvTotal-self.rcvTotalLast)//periodStatistics
            self.rcvTotalValueLabel.setText("{:^d}".format(self.rcvTotal))
            self.rcvSpeedValueLabel.setText("{:^.0f}".format(rcvSpeed))
            self.sndTotalValueLabel.setText("{:^d}".format(self.sndTotal))
            self.sndSpeedValueLabel.setText("{:^.0f}".format(sndSpeed))
            # 更新历史记录
            self.sndTotalLast = self.sndTotal
            self.rcvTotalLast = self.rcvTotal
            sleep(periodStatistics)

#     # 清除记录按钮
#     self.pushButtonClear
    @QtCore.pyqtSlot()
    def on_pushButtonClear_pressed(self):
        self.textEditSend.clear()
        self.rcvTotal = 0
        self.rcvTotalLast = 0
        self.sndTotal = 0
        self.sndTotalLast = 0
        self.comboBoxSndHistory.clear()
        if debug == True:
            logging.debug("清除接收区以及发送区")


    def changezichuankou(self):
        self.zichuankou = 0
        QMessageBox.warning(self,"子窗口关闭","子窗口关闭其资源全部关闭")

# 文件菜单栏Action
    @QtCore.pyqtSlot(bool)
    def on_action_shutdown_triggered(self,checked):
        if debug == True:
            logging.debug("点击了退出按钮:{}".format(checked))

    def closeEvent(self, event):
        reply = QMessageBox.question(self,'提示',"确认退出吗？",QMessageBox.Yes | QMessageBox.No,QMessageBox.No)
        if reply == QMessageBox.Yes:
            event.accept()
            os._exit(0)
        else:
            event.ignore()
        try:
            self.csv_file_1.close()
        except:
            QMessageBox.critical(self,'关闭文件失败','未知原因导致关闭文件失败')

        try:
            self.mythread1.stop()
        except Exception as e:
            QMessageBox.critical(self,'没有文件可以关闭','关闭保存文件失败')


    @QtCore.pyqtSlot()
    def on_pushButtonChart_clicked(self):
        if self.com.getPortState():
            self.w_chart = Mywin()
            self.w_chart.show()
            self.zichuankou = 1 #让主界面知道子窗口打开了，当zichuangkou变量为1，dict才会发信号传数据
            self.dictsignal.connect(self.w_chart.slotTimeout)
            self.w_chart.closesignal.connect(self.changezichuankou) #点击按钮连接关闭给主UI状态
        else:
            QMessageBox.warning(self,"串口未打开","串口没有打开，打开串口接收数据才能打开绘图界面")
        
    #界面按钮手动连接~~~
    def map_create_cb(self):   #呈现到leftwidget
        if self.mapDict !={}:
            my_dict = self.mapDict
            with open(os.path.abspath('userchoose.csv'),'w',newline="") as f:
                writer1 = csv.writer(f)
                a = 'address'
                b = 'name'
                writer1.writerow([a,b])
                for key,value in my_dict.items():
                    writer1.writerow([key,value])
        else:
            QMessageBox.warning(self,'保存map文件到csv','保存CSV失败，可能由于您没解析MAP文件')
        try:
            my_dict = self.mapDict
            self.leftWidget.clear()
            for value in my_dict.values():
                item = QListWidgetItem()
                item.setText(value)
                curRow = self.leftWidget.currentRow() #当前行，目前没有用
                self.leftWidget.addItem(item)
        except:
            QMessageBox.warning(self,'参数错误','您还没有生成变量')

    def mapparser_cb(self):
        self.map_file_name = QFileDialog.getOpenFileName(self,"打开map文件",'C:\\',"Map files(*.map)")
        print(self.map_file_name) #返回了文件绝对路径file_name[0]为绝对路径，即C:\XXXX\XXX\XXX.map
        if self.map_file_name[0]:
            self.mapConfig,self.mapDict = self.mapToJson(self.map_file_name[0])
        else:
            QMessageBox.warning(self,'没有选择文件','可以再次选择map文件！')
    
    def list_remove_item(self):
        row = self.listWidget.currentRow()
        self.listWidget.takeItem(row)
    
    def list_clear_cb(self):
        self.listWidget.clear()

    def save_file_thread(self):
        if self.com.getPortState():
            if not os.path.exists('./data'):
                os.mkdir('./data')
            if not os.path.exists('./data/datafile'):
                os.mkdir('./data/datafile')
            try:
                self.file_name1 = "data/datafile/" + utils.get_current_date() + ".csv"
                # self.csv_file_1 = open(file_name1,'a+',newline='')
                # self.writer_1 = csv.writer(self.csv_file_1)
                # 改为dataframe储存
                self.save_df = pd.DataFrame() #清空dataframe
                self.mythread1 = RunThread1(self)
                self.mythread1.start()
            except Exception as e:
                QMessageBox.warning(self,"打开文件错误","打开文件错误，请检查")
        else:
            QMessageBox.warning(self,"串口未打开","打开串口接收数据再点击该按钮")
    
    def save_file_cancel(self):
        try:
            self.save_df.to_csv(self.file_name1,index=False,mode='a')
            self.save_df = pd.DataFrame()
            QMessageBox.critical(self,'保存文件成功','保存文件成功，清空DataFrame成功！')
        except:
            QMessageBox.critical(self,'保存文件失败','保存文件失败，清空DataFrame失败!!!')
            pass

        try:
            self.mythread1.stop()
        except:
            QMessageBox.critical(self,'线程停止失败','线程停止失败！！！')
            pass

    #生成指令按钮后生成指令
    def create_order(self):
        QMessageBox.warning(self,"每次生成指令","都要清空user_para_dict以及self_para_addr但全局变量生成的指令不会清空")
        if self.listWidget.count() >= 1:
            para_list = []
            for i in range(self.listWidget.count()):
                aItem = self.listWidget.item(i)
                print(aItem.text()) #打印了AVMBlob_initAVMInterval_emptyinit
                para_list.append(aItem.text())
            #para_list为['AVMInterval_emptyinit', 'AVMInterval_assign']用户选择的参数字符串
            #现在要去找对应的地址
            self.user_para_dict = {}
            self.user_para_addr = []

            for i in para_list:
                addr = list(self.mapDict.keys())[list(self.mapDict.values()).index(i)]
                #现在找到了用户选择的参数的地址,也就是dict中的key，现在要把地址组装
                self.user_para_addr.append(addr)
                self.user_para_dict[addr] = i
            print('用户选择的地址列表为：',self.user_para_addr)
            print('用户选择的参数dict为：',self.user_para_dict)
            #然后把指令显示['0c061108', '0c068498'],帧头（2字节）+有效长度（1字节）+命令字（1字节）+地址1（4字节）+长度（1字节）
            #+地址2（4字节）+长度（1）字节,长度是固定'04'【传输显示04】
            frame_tou = 'E116' # 帧头固定的，那么有小长度占1字节，组装（'E116220c06110800010c068498'）
            frame_type = '22' # 固定的命令字
            frame_sigle_lang = '01' #固定每个参数宽度,不一定是4~~~~~~@@,给DSP的地址长度
            frame_datas = ''  #变量位加上它自己的sigle长度位
            for i in range(len(self.user_para_addr)):
                one_datazhen = self.user_para_addr[i] + frame_sigle_lang #注意这里固定了一个参数带的数据的字节数为1@@@@
                frame_datas = frame_datas + one_datazhen  #这里5个字节了@@@@@
            print('数据位+自己的single长度字符显示',frame_datas)
            temp1 = str(hex(len(self.user_para_addr) * 5)) #用户选择n个变量，那么长度位就是5*n,@@#temp=有效长度位
            print(temp1)
            #我要把0xa转换为'0A'
            if len(self.user_para_addr) * 5 < 16:
                frame_changdu = '0'+ temp1.replace('0x','')
            else:
                frame_changdu = temp1.replace('0x','')
            print('长度位大小字符显示：',frame_changdu) #打印长度位情况
            print('长度位大小int显示：',int(frame_changdu,16))
            #下面是除开校验位checksum以外的str表达的帧
            frame_exceptchecksum = frame_tou + frame_changdu + frame_type + frame_datas
            print(frame_exceptchecksum) #OK现在除开校验位正确了
            
            #下面就是生产校验位了
            if frame_exceptchecksum:
                checksum = 0
                for i,j in zip(frame_exceptchecksum[8::2],frame_exceptchecksum[9::2]):
                    checksum += int('0x' + (i + j),16)
                print('发送的校验和未取第2字节:',checksum)
                check_num = ('{:04x}'.format(checksum & 0xFFFF)).upper() #【更变！】~~~~~
                send_code = frame_exceptchecksum + ('00'*(240-len(self.user_para_addr)*5-2-1-1-2)) +check_num
                self.lineEdit_2.setText(send_code)
                self.lineEdit_2.setReadOnly(True)
                #生产指令完毕
            else:
                QMessageBox.warning(self,"无法生产指令","程序没有收到选择参数")
        else:
            QMessageBox.warning(self,"请选择参数","请选择想要获取的参数")

    def create_order_send(self):
        if self.com.getPortState() == True:
            if self.lineEdit_2.text():
                sendddd = self.lineEdit_2.text().upper()
                # 发送
                try:
                    buf = bytes.fromhex(sendddd)
                    print('buf的发送数值为：',buf)
                    self.com.send(buf)
                    self.sndTotal += len(buf)
                    QMessageBox.warning(self,'发送成功','发送成功')  
                except:
                    QMessageBox.warning(self,'发送失败','发送失败')    
                print(sendddd)
                self.user_send_message = sendddd
                self.user_send_length = len(self.user_para_addr)
            else:
                QMessageBox.warning(self,"暂未生产指令！","请先生产指令")
        else:
            QMessageBox.warning(self,"请先打开串口","请先打开串口")
        #self.table1.setRowCount(5) #后面需要根据用户选择数量进行更变

    #bin文件2个按钮的回调函数
    def bin_file_cb(self):
        self.bin_file_name,ok = QFileDialog.getOpenFileName(self,"打开bin文件",'C:\\',"Bin files(*.*)")
        print(self.bin_file_name) #返回了文件绝对路径file_name[0]为绝对路径
        if ok:
            self.lineEdit.setText(str(self.bin_file_name))
        else:
            QMessageBox.warning(self,"还未选择bin文件",'请选择你要发送的bin文件')
    
    #点击发送bin文件按钮，开启线程，吧tabWidget关闭
    def send_bin_cb(self): 
        try:
            if self.com.getPortState():
                if self.bin_file_name[0]:
                    #self.tabWidget.setEnabled(False)
                    self.bin_send_thread.start()
                else:
                    QMessageBox.warning(self,"未选择bin文件","请先选择bin文件再发送")
            else:
                QMessageBox.warning(self,"串口未打开","先打开串口才能发送")
        except:
            QMessageBox.warning(self,"开始发送bin文件","发送失败，原因未知")
        

    #定义点击echatrs显示按钮函数
    def show_echarts(self):
        try:
            file_path = self.csv_name #先把csv文件绝对路径放入file_path
            csv_data = pd.read_csv(file_path,low_memory = False) 
            csv_df = pd.DataFrame(csv_data)
            #先获取列名-变成中文名给echarts的legend，@@@非常重要列名
            df_name = [column for column in csv_df]
            keylist = []
            for key in df_name:
                if key == "time":
                    break
                CN_name = self.df.loc[self.df.address == key.lower(),'CN_name'].values[0]
                keylist.append(CN_name)
            
            #声明一个列准备传给js
            csv_list = []
            for key in df_name:
                #下面代码很重要，输出列
                csv_list.append(csv_df[key].tolist())
        except:
            QMessageBox.warning(self,"未选择csv文件","请先选择csv文件后点击显示图形")
        

        js  = "setValue({},{})".format(csv_list,keylist)
        self.webView2.page().runJavaScript(js)
        # except:
        #     QMessageBox.warning(self,'请选择csv文件','请选择csv文件后才能展示数据')
            
            
    def choosecsv(self):
        self.csv_name,ok = QFileDialog.getOpenFileName(self,"打开csv文件",'./data/datafile',"csv files(*.csv)")
        print(type(self.csv_name)) #返回了文件绝对路径file_name[0]为绝对路径
        if ok:
            self.lineEdit_3.setText(str(self.csv_name))
        else:
            QMessageBox.warning(self,"还未选择csv文件",'请选择你要发送的csv文件')
        
        
        



    #~~~~~~~~~~~~非被信号连接的函数，是函数连接的函数~~~~~~~~~~
    ##生成指令用到的链接函数
    def mapToJson(self,name):#解析map文件函数，返回一个变量列表，一个变量dict
        map_config = []
        map_dict = {}
        filename = name
        if filename:
            QMessageBox.warning(self,"找到MAP文件","找到map文件")
        else:
            QMessageBox.warning(self,"没有找到文件","没有找到相对应的map文件")

        with open(filename, 'r') as f:  #这里要改
            read = f.readlines()
            start_index = 0
            end_index = len(read)
            try: #直接在这里
                start_index = list.index(read, 'GLOBAL SYMBOLS: SORTED ALPHABETICALLY BY Name \n') + 4
                end_index = list.index(read, 'GLOBAL SYMBOLS: SORTED BY Symbol Address \n') - 3
            except Exception as e:
                print('未找到匹配的地址信息,解析过程可能稍慢，请耐心等待。')
            read = read[start_index:end_index]
            if start_index > 0:  # 匹配到开始结束位时，直接读取整个列表添加到数组中
                for t in read:
                    t = t.strip('\n')
                    t = t.split(' ')
                    if t[0][-4:] not in map_dict.keys():
                        map_dict[t[0][-8:]] = t[-1]
                        map_config.append({'value': t[0][-8:], 'desc': t[-1]})
            else:  # 未匹配到开始结束位时，就把列表循环。一般不会出现这种情况
                for t in read:
                    t = t.strip('\n')
        return map_config, map_dict

#~~~~~~~~~~~~~~~~~~~~~~~~~~自定义信号连接函数~~~~~~~~~~~~~~~~~~~~~~~~~~
#接收函数1-用来处理UI展示接收字节数量
    @QtCore.pyqtSlot(int)
    def on_com_signalRcv(self,count):
        self.rcvTotal += count #记录数据的
        print('获取的数量展示为~~~：',self.rcvTotal)

#接收函数2-用来传递dict数据给子窗口以及其他用处
    @QtCore.pyqtSlot(dict)
    def on_com_signalRcvdata(self,data_dict):
        if bool(data_dict):
            print("UI界面获取的dict为：",data_dict)

            if self.zichuankou == 1: #如果子窗口被打开了，发出数据
                self.dictsignal.emit(data_dict)

            #循环显示keys,放入listWidget,注意这里@@@@@@@@@缺少对其判断@@@@@@@@@
            try:
                recive_para = []
                recive_para_CN = []
                for key in data_dict.keys():
                    recive_para.append(key)
                for key in data_dict.keys():
                    CN_address = self.df.loc[self.df.address == key.lower(),'CN_name'].values[0] #获取中文名字
                    recive_para_CN.append(CN_address)

                for j in range(2):
                    for i in range(len(data_dict)):
                        if j == 0:
                            self.table1.setItem(i,j,QTableWidgetItem(recive_para_CN[i]))
                        elif j == 1:
                            self.table1.setItem(i,j,QTableWidgetItem(data_dict[recive_para[i]]))
            except:
                print('变量地址不存在变量库中，无法生成中文名....')
                pass

            '''
            #给储存文件的值
            a = {"a":1}
            #变成
            a = {"b":1}
            #方法
            a["b"]=a.pop("a")
            '''
            data_dict["time"] = utils.get_current_hour()
            self.save_dict = data_dict


    #接收错误数据信号连接函数
    @QtCore.pyqtSlot(str)
    def on_com_signalRcvError(self,txt):
        if debug == True:
            logging.error("串口异常关闭:{}".format(txt))
        #
        self.on_pushButtonOpen_toggled(False)
        # 更新串口列表
        self.update_comboBoxPortList()
        pass

    def text_display(self,text):
        self.textEdit.append(text)

class RunThread1(QtCore.QThread):
    def __init__(self,parent):
        super().__init__()
        self.parent = parent #将主界面信息传过来
    
    def run(self): #接收主线程送来的信号进行保存
        while True:
            #存入dataframe
            self.parent.save_df = self.parent.save_df.append(self.parent.save_dict,ignore_index=True)
            time.sleep(0.1) #注意以后改
            
    def stop(self):
        self.terminate()
class Send_bin_Thread(QtCore.QThread):
    sin_out = QtCore.pyqtSignal(str)
    def __init__(self,parent):
        super().__init__()
        self.parent = parent

    def run(self):
        self.sin_out.emit('开始......')
        self.sin_out.emit('发送重构代码指令......')
        self.sin_out.emit('读取指令模板......')
        ZT1 = 'EB'
        ZT2 = '90'
        MLZ = '44'
        #先发送重构bin文件指令，先获取bin文件字节长度
        self.sin_out.emit('读取二进制bin文件......')
        file_bin = open(self.parent.bin_file_name,"rb") #二进制读取bin文件

        self.sin_out.emit('正在获取二进制bin文件byte数据......')
        bin_data = file_bin.read() #把全部byte读出来
        self.sin_out.emit('二进制文件数据为：{}'.format(bin_data))

        self.sin_out.emit('正在获取二进制bin文件byte数据的长度......')
        bin_length = len(bin_data)  #把字节长度读出来
        self.sin_out.emit(f'byte数据的长度为{bin_length}......')

        #准备发送重构代码指令
        bin_len_bao_num = bin_length//240 #bin_len_bao表示有多少个240字节的包
        baonum = "".join("{:02X}".format(bin_len_bao_num))

        bin_len_shengxia = bin_length%240  #bin_len_shengxia表示除开240字节包后还剩多少字节
        shengxiawei = "".join("{:02X}".format(bin_len_shengxia))

        self.sin_out.emit('准备发送重构指令，240字节指令......')

        send_order = ''.join([ZT1,ZT2,'02',MLZ,baonum,shengxiawei]) #这里02可能要改@@@@@
        self.sin_out.emit('组合现在的指令为{}......'.format(send_order))

        #生产校验位,并发送重构指令
        checksum = 0
        for i,j in zip(send_order[8::2],send_order[9::2]):
            checksum += int('0x' + (i + j),16)
        check_num = ('{:04x}'.format(checksum & 0xFFFF)).upper() #【更变！】~~~~~
        send_code = send_order + ('00'*(238-len(send_order)//2)) +check_num

        self.sin_out.emit('重构指令生成成功......发送完毕！')
        buf = bytes.fromhex(send_code)
        self.parent.com.send_order(buf)
        self.sin_out.emit('发送完毕！，开始发送代码包')
        time.sleep(5)

        #开始发送包
        #先将bin_data变成字符串480个字符（240字节）
        bin_data_str = "".join(["{:02X}".format(i) for i in bin_data])
        self.sin_out.emit('需要发送的数据为：{}'.format(bin_data_str))
        self.sin_out.emit('需要发送的数据长度位为：{}'.format(len(bin_data_str)))
        for i in range(bin_len_bao_num): #整包发一次
            temp1 = bin_data_str[i*480:i*480+480]
            buf1 = bytes.fromhex(temp1)
            self.parent.com.send_order(buf1)
            self.sin_out.emit('当前发送的包序号为：{}'.format(i+1))
            time.sleep(1)
        #最后小包发一次
        temp2 = bin_data_str[bin_len_bao_num*480:]
        buf2 = bytes.fromhex(temp2)
        self.parent.com.send_order(buf2)
        self.sin_out.emit('当前发送的包序号为尾包')
        time.sleep(1)
        self.sin_out.emit('发送完毕')
        

                



if __name__ == "__main__":
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)
    win = userMain()

    qtmodern.styles.light(app) #还有dark可以选择
    mw = qtmodern.windows.ModernWindow(win)
    mw.show()
    # win.show()

    sys.exit(app.exec_())