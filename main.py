import time
import pycom
from pysense import Pysense
import machine
from machine import Pin
from machine import Timer
#######  Import Sensores
from SI7006A20 import SI7006A20
from LIS2HH12 import LIS2HH12
from LTR329ALS01 import LTR329ALS01
from MPL3115A2 import MPL3115A2,ALTITUDE,PRESSURE
########### Import MQTT
import network
import usocket
import ubinascii
from mqtt import MQTTClient
import sys
########### Import Bluetooth
from network import Bluetooth

# Button definition
botao = Pin('P14', mode=Pin.IN, pull=Pin.PULL_UP)

pycom.heartbeat(False)
pycom.rgbled(0x0A0A08) # white

py = Pysense()
#LER TSensores
si = SI7006A20(py)
mp = MPL3115A2(py,mode=ALTITUDE) # Returns height in meters. Mode may also be set to PRESSURE, returning a value in Pascals
mpp = MPL3115A2(py,mode=PRESSURE)
lt = LTR329ALS01(py)
li = LIS2HH12(py)
t_ambient = 24.4

#Variável auxiliar - guarda o estado do interruptor
variavel = 0


# setup as a station
wlan = network.WLAN(mode=network.WLAN.STA)
wlan.connect('MEO-8D0BF0', auth=(network.WLAN.WPA2, '7ccc98eb74'))

while not wlan.isconnected():
     machine.idle() # save power while waiting

print("%============================%")
print("% WLAN Connected             %")
print("%============================%")

print("Config:", wlan.ifconfig())
pycom.rgbled(0x0000FF) # Blue


############### Bluetooth Low Energy

bluetooth = Bluetooth()
bluetooth.set_advertisement(name='LoPy do ABCD', service_uuid=b'1234567890123456') #Define o nome e o ID

#Avisa caso haja uma nova conexão/desconexão de um dispositivo ao LoPy através de BLE
def conn_cb (bt_o):
    events = bt_o.events()
    if  events & Bluetooth.CLIENT_CONNECTED:
	print("Conectado através de BLE")
    elif events & Bluetooth.CLIENT_DISCONNECTED:
	print("Desconectado através de BLE")

bluetooth.callback(trigger=Bluetooth.CLIENT_CONNECTED | Bluetooth.CLIENT_DISCONNECTED, handler=conn_cb)

bluetooth.advertise(True)

srv1 = bluetooth.service(uuid=b'1234567890123456', isprimary=True)
chr1 = srv1.characteristic(uuid=b'1234567890123456', value="Redes de Sensores") #Mensagem que o LoPy escreve através do BLE


#Dependendo da mensagem recebida,do dispositivo através de BLE, comuta o estado do interruptor
def char1_cb(chr):
    print("Write request with value = {}".format(chr.value()))
    if (chr.value() == b"ON"):
        #print("Interruptor ON - BLE")
        client.publish(topic="samymh/feeds/botao", msg = "ON")
    if (chr.value() == b"OFF"):
        #print("Interruptor OFF - BLE")
        client.publish(topic="samymh/feeds/botao", msg = "OFF")

char1_cb = chr1.callback(trigger=Bluetooth.CHAR_WRITE_EVENT, handler=char1_cb)

###############

#Caso haja comutação do interruptor através: Adafruit/MQTT.fx, Botão LoPy ou do telemóvel(BLE)
#Ou seja, quando o client.check_msg() deteta uma mensagem = 'ON' ou 'OFF'
def sub_cb(topic, msg):
   print(msg)
   global variavel
   if msg == b"ON":
      print("Interruptor ON")
      variavel = 1
      pycom.rgbled(0x00FF00) # GREEN
   if msg == b"OFF":
      print("Interruptor OFF")
      variavel= 0
      pycom.rgbled(0xFF0000) # RED
      #Reset dos feeds do dashboard
      client.publish(topic="samymh/feeds/temperatura0", msg = "0" )
      client.publish(topic="samymh/feeds/bateria", msg="0")
      client.publish(topic="samymh/feeds/luminiosidade", msg="0")
      client.publish(topic="samymh/feeds/humidade", msg="0")
      client.publish(topic="samymh/feeds/temperatura", msg = "0" )

client = MQTTClient("RS 2020 - 19/11", "io.adafruit.com",user="samymh", password="aio_KovO75Hpc8XnmsAwGTpjFntCDQTd", port=1883)

client.set_callback(sub_cb)
client.connect()

#Subscrever feed do adafruit
#Permite receber informação, do feed subscrito, através dos callbacks(quando ocorre interrupção)
client.subscribe(topic = "samymh/feeds/botao")


#Contador de 30s que permite atualizar os dados peridodicamente
#Útil para poder fazer o check_msg() rapidamente
#Se metessemos isto no while() tinhamos de meter um deelay muito grande para não ocupar a banda ISM.
#E podiamos perder informação - perder "msg"
class Clock:
    def __init__(self):
        self.seconds = 29
        self.__alarm = Timer.Alarm(self._seconds_handler, 1, periodic=True)
    def _seconds_handler(self, alarm):
        self.seconds += 1
        if self.seconds == 30:
            print("Timer TICK")
            #Se interruptor esta ligado
            if variavel == 1:
                print("Data UPDATED")
                #Publicar os dados nos feeds do Adafruit
                client.publish(topic="samymh/feeds/temperatura0", msg = str(si.temperature()) )
                client.publish(topic="samymh/feeds/temperatura", msg = str(si.temperature()) )
                client.publish(topic="samymh/feeds/bateria", msg=(str(py.read_battery_voltage())))
                client.publish(topic="samymh/feeds/luminiosidade", msg=str(lt.light()[1]))
                client.publish(topic="samymh/feeds/humidade", msg=(str(si.humidity())))
                #Imprimir os dados
                print("Temperature: " + str(si.temperature())+ " ºC ")
                print("Relative Humidity: " + str(si.humidity()) + " %RH")
                print("Humidity Ambient for " + str(t_ambient) + " deg C is " + str(si.humid_ambient(t_ambient)) + "%RH")
                print("Luminosity: " + str(lt.light()) + "Lux")
                print("Battery voltage: " + str(py.read_battery_voltage()) + "V")
                print("Acceleration: " + str(li.acceleration()) +  "  Roll: " + str(li.roll()) + "  Pitch: " + str(li.pitch()) )

            #Se o interruptor estiver desligado
            else:
                machine.idle() # save power while waiting
            self.seconds = 0

clock = Clock()


while True:
    #Sempre que o botão do LoPy é pressionado, o estado do interruptor é comutado
    if ((botao()==0)):
        if (variavel == 0) :
            client.publish(topic="samymh/feeds/botao", msg = "ON") #Habilita interruptor
        else:
            client.publish(topic="samymh/feeds/botao", msg = "OFF")#Desabilita interruptor

    time.sleep(1)
    #print("Variavel: "+ str(variavel))

    #Verificar se há pedido para comutar o estado do Interruptor
    #Caso msg='ON'   --> Interruptor ON
    #Caso msg='OFF'  --> Interruptor OFF
    client.check_msg()
