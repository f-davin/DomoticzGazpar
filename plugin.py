#           Gazpar Plugin
#
#           Author: 
#                       Copyright (C) 2020 DavTechNet
#
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""
<plugin key="Gazpar" name="Compteur gaz Gazpar" author="DavTechNet" version="0.0.1" externallink="https://github.com/DavTechNet/DomoticzGazpar">
    <description>
        <h2>Gazpar plugin</h2><br/>
        This plugin permits the get the gas consommation information from the GRDF website.
        <h3>Configuration</h3>
        Enter the information about identification of the GRDF website and all the configuration is done.
    </description>
    <params>
        <param field="Mode6" label="Debug" width="100px">
            <options>
                <option label="True" value="Debug"/>
                <option label="False" value="Normal"  default="true" />
            </options>
        </param>
    </params>
</plugin>
"""

import Domoticz
import sys
import json
from datetime import datetime
from datetime import timedelta
from datetime import time
from time import strptime

DAYS_FILENAME       = "export_days_values.json"
DAYS_FILE_LOCATION  = "/opt/domoticz/plugins/domoticz_gaspar/"

class BasePlugin:
    # boolean: to check that we are started, to prevent error messages when disabling or restarting the plugin
    isStarted = None
    # integer: index of the Linky device
    iIndexUnit = 1
    # string: name of the Linky device
    sDeviceName = "Gazpar"
    # string: description of the Linky device
    sDescription = "Compteur Gazpar"
    # integer: type (pTypeGeneral)
    iType = 0xF3
    # integer: subtype (sTypeManagedCounter)
    iSubType = 0x21
    # integer: switch type (Energy)
    iSwitchType = 0
    # boolean: debug mode
    iDebugLevel = None

    def __init__(self):
        self.isStarted = False

    def myDebug(self, message):
        if self.iDebugLevel:
            Domoticz.Log(message)

    # Create Domoticz device
    def createDevice(self):
        # Only if not already done
        if not self.iIndexUnit in Devices:
            Domoticz.Device(Name=self.sDeviceName,  Unit=self.iIndexUnit, Type=self.iType, Subtype=self.iSubType, Switchtype=self.iSwitchType, Description=self.sDescription, Used=1).Create()
            if not (self.iIndexUnit in Devices):
                Domoticz.Error("Ne peut ajouter le dispositif Gazpar à la base de données. Vérifiez dans les paramètres de Domoticz que l'ajout de nouveaux dispositifs est autorisé")
                return False
        return True

    # Create device and insert usage in Domoticz DB
    def createAndAddToDevice(self, usage, Date):
        if not self.createDevice():
            return False
        # -1.0 for counter because Gazpar doesn't provide absolute counter value via Enedis website
        sValue = "-1.0;"+ str(usage) + ";"  + str(Date)
        self.myDebug("Mets dans la BDD la valeur " + sValue)
        Devices[self.iIndexUnit].Update(nValue=0, sValue=sValue, Type=self.iType, Subtype=self.iSubType, Switchtype=self.iSwitchType)
        return True

    # Update value shown on Domoticz dashboard
    def updateDevice(self, usage):
        if not self.createDevice():
            return False
        # -1.0 for counter because Gazpar doesn't provide absolute counter value via GRDF website
        sValue="-1.0;"+ str(usage)
        self.myDebug("Mets sur le tableau de bord la valeur " + sValue)
        Devices[self.iIndexUnit].Update(nValue=0, sValue=sValue, Type=self.iType, Subtype=self.iSubType, Switchtype=self.iSwitchType)
        return True

    # Calculate next complete grab, for tomorrow between 5 and 6 am if tomorrow is true, for next hour otherwise
    def setNextConnection(self):
        # Next treatment, tomorrow 6:00 pm
        #self.nextConnection = datetime.now() + timedelta(minutes=1)
        #Domoticz.Log('Next connection: ' + str(self.nextConnection))
        self.nextConnection = datetime.now() + timedelta(days=1)
        self.nextConnection = self.nextConnection.replace(hour=18)

    # Grab days data inside received JSON data for history
    def exploreDataDays(self):

        try:
            with open(DAYS_FILE_LOCATION + DAYS_FILENAME, 'r') as json_file:
                #Domoticz.Log('content: ' + json_file.read())
                dJson = json.loads(json_file.read())
                #Domoticz.Log('json: ' + str(dJson))
        except ValueError as err:
            Domoticz.Log("Les données reçues ne sont pas du JSON : " + str(err))
            return False
        except TypeError as err:
            Domoticz.Log("Le type de données reçues n'est pas JSON : " + str(err))
            return False
        except:
            Domoticz.Log("Erreur dans les données JSON : " + str(sys.exc_info()[0]))
            return False
        else:
            for item in dJson:
                try:
                    val = float(item['conso']) * 1000.0
                except:
                    val = -1.0

                if (val >= 0.0):
                    sDate = enedisDateToDatetime(item['time'])
                    if not self.createAndAddToDevice(val, datetimeToSQLDateString(sDate)):
                        return False

    def onStart(self):
        Domoticz.Log("onStart called")

        try:
            self.iDebugLevel = int(Parameters["Mode6"])
        except ValueError:
            self.iDebugLevel = 0
    
        if self.iDebugLevel > 1:
            Domoticz.Debugging(1)
        
        # most init
        self.__init__()

        if self.createDevice():
            self.nextConnection = datetime.now()
        else:
            self.setNextConnection()

        # Now we can enabling the plugin
        self.isStarted = True

    def onStop(self):
        Domoticz.Log("onStop called")
        self.isStarted = False

    def onConnect(self, Connection, Status, Description):
        Domoticz.Log("onConnect called")

    def onMessage(self, Connection, Data):
        Domoticz.Log("onMessage called")

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Log("onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Log("Notification: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self, Connection):
        Domoticz.Log("onDisconnect called")

    def onHeartbeat(self):
        Domoticz.Log("onHeartbeat called")

        if datetime.now() > self.nextConnection:
            # Define the next treatment
            self.setNextConnection()

            # treatment of data
            self.exploreDataDays()
            Domoticz.Log('Terminated')
            

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)

def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

    # Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return


# Convert datetime object to Domoticz date string
def datetimeToSQLDateString(datetimeObj):
    return datetimeObj.strftime("%Y-%m-%d")

# Convert Enedis date string to datetime object
def enedisDateToDatetime(datetimeStr):
    #Buggy
    #return datetime.strptime(datetimeStr, "%d/%m/%Y")
    #Not buggy ?
    return datetime(*(strptime(datetimeStr, "%d/%m/%Y")[0:6]))