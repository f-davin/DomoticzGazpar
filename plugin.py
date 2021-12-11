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
<plugin key="Gazpar" name="Compteur gaz Gazpar" author="DavTechNet" version="0.1.0" externallink="https://github.com/DavTechNet/DomoticzGazpar">
    <description>
        <h2>Gazpar plugin</h2><br/>
        This plugin permits the get the gas consommation information from the GRDF website.
        Based on https://github.com/Scrat95220/DomoticzGazpar.git.
        <h3>Configuration</h3>
        Enter the following informations to configure the plugin:
        <ul style="list-style-type:square">
            <li>GRDF site login</li>
            <li>GRDF site password</li>
            <li>Number of days to import</li>
            <li>Debug option</li>
        </ul>
    </description>
    <params>
        <param field="Mode1" label="GRDF login" required="true" default="" width="200px" />
        <param field="Mode2" label="GRDF Password" required="true" default="" width="200px" password="true" />
        <param field="Mode3" label="Days to import (1-150)" required="true" default="150" width="150px" />
        <param field="Mode4" label="PCE identification point" required="true" default="" width="150px" />
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
import requests
import json
from datetime import datetime
from dateutil.relativedelta import relativedelta
import urllib.request

LOGIN_BASE_URI = 'https://login.monespace.grdf.fr/sofit-account-api/api/v1/auth'
API_BASE_URI = 'https://monespace.grdf.fr/'


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
    # Username for GRDF website
    username = None
    # Password for GRDF website
    password = None
    # History to read in day
    nb_days = 1
    # PCE point
    pce = None
    # State machine
    sConnectionStep = None
    # Session of connection
    session = None

    def __init__(self):
        self.isStarted = False
        self.sConnectionStep = "idle"

    def logDebug(self, message):
        if self.iDebugLevel:
            Domoticz.Log(message)

    # Create Domoticz device
    def createDevice(self):
        # Only if not already done
        if not self.iIndexUnit in Devices:
            Domoticz.Device(Name=self.sDeviceName, Unit=self.iIndexUnit, Type=self.iType, Subtype=self.iSubType,
                            Switchtype=self.iSwitchType, Description=self.sDescription, Used=1).Create()
            if not (self.iIndexUnit in Devices):
                Domoticz.Error(
                    "Ne peut ajouter le dispositif Gazpar à la base de données. Vérifiez dans les paramètres de Domoticz que l'ajout de nouveaux dispositifs est autorisé")
                return False
        return True

    # Create device and insert usage in Domoticz DB
    def createAndAddToDevice(self, usage, Date):
        if not self.createDevice():
            return False
        self.addToDevice(usage, Date)
        return True

    # insert usage in Domoticz DB
    def addToDevice(self, fConsumption: float, sDate: str):
        # -1.0 for counter because Gazpar doesn't provide absolute counter value via Enedis website
        sValue = "-1.0;" + str(fConsumption) + ";" + sDate
        self.logDebug("Mets dans la BDD la valeur " + sValue)
        Devices[self.iIndexUnit].Update(nValue=0, sValue=sValue, Type=self.lType, Subtype=self.iSubType,
                                        Switchtype=self.iSwitchType)

    # Update value shown on Domoticz dashboard
    def updateDevice(self, usage):
        if not self.createDevice():
            return False
        # -1.0 for counter because Gazpar doesn't provide absolute counter value via GRDF website
        sValue = "-1.0;" + str(usage)
        self.logDebug("Mets sur le tableau de bord la valeur " + sValue)
        Devices[self.iIndexUnit].Update(nValue=0, sValue=sValue, Type=self.iType, Subtype=self.iSubType,
                                        Switchtype=self.iSwitchType)
        return True

    # Calculate next complete grab, for tomorrow between 5 and 6 am if tomorrow is true, for next hour otherwise
    def setNextConnection(self):
        # Next treatment, tomorrow 6:00 pm
        # self.nextConnection = datetime.now() + timedelta(minutes=1)
        # Domoticz.Log('Next connection: ' + str(self.nextConnection))
        self.nextConnection = datetime.now() + timedelta(days=1)
        self.nextConnection = self.nextConnection.replace(hour=18)

    def checkDomoticzVersion(self):
        """
        Check the version of Domoticz
        :return: True if version is superior, False otherwise
        """
        ret = False
        matchVersions = re.search(r"(\d+)\.(\d+)", Parameters["DomoticzVersion"])
        if (matchVersions):
            iVersionMaj = int(matchVersions.group(1))
            iVersionMin = int(matchVersions.group(2))
            iVersion = (iVersionMaj * 1000000) + iVersionMin
            if iVersion >= 4011774:
                ret = True
        return ret

    def login(self):
        """Logs the user into the GRDF API.
        """
        session = requests.Session()

        payload = {
            'email': self.username,
            'password': self.password,
            'goto': 'https://sofa-connexion.grdf.fr:443/openam/oauth2/externeGrdf/authorize?response_type=code%26scope=openid%20profile%20email%20infotravaux%20%2Fv1%2Faccreditation%20%2Fv1%2Faccreditations%20%2Fdigiconso%2Fv1%20%2Fdigiconso%2Fv1%2Fconsommations%20new_meg%20%2FDemande.read%20%2FDemande.write%26client_id=prod_espaceclient%26state=0%26redirect_uri=https%3A%2F%2Fmonespace.grdf.fr%2F_codexch%26nonce=7cV89oGyWnw28DYdI-702Gjy9f5XdIJ_4dKE_hbsvag%26by_pass_okta=1%26capp=meg',
            'capp': 'meg'
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Referer': 'https://login.monespace.grdf.fr/mire/connexion?goto=https:%2F%2Fsofa-connexion.grdf.fr:443%2Fopenam%2Foauth2%2FexterneGrdf%2Fauthorize%3Fresponse_type%3Dcode%26scope%3Dopenid%2520profile%2520email%2520infotravaux%2520%252Fv1%252Faccreditation%2520%252Fv1%252Faccreditations%2520%252Fdigiconso%252Fv1%2520%252Fdigiconso%252Fv1%252Fconsommations%2520new_meg%2520%252FDemande.read%2520%252FDemande.write%26client_id%3Dprod_espaceclient%26state%3D0%26redirect_uri%3Dhttps%253A%252F%252Fmonespace.grdf.fr%252F_codexch%26nonce%3D7cV89oGyWnw28DYdI-702Gjy9f5XdIJ_4dKE_hbsvag%26by_pass_okta%3D1%26capp%3Dmeg&realm=%2FexterneGrdf&capp=meg'
        }

        resp1 = session.post(LOGIN_BASE_URI, data=payload, headers=headers)
        Domoticz.Debug("1st Auth Response : \n" + resp1.text)
        if resp1.status_code != requests.codes.ok:
            print("Login call - error status :" + resp1.status_code + '\n');
            Domoticz.Error("Login call - error status :" + resp1.status_code + '\n')
            raise RuntimeError("Login call - error status :" + resp1.status_code)

        j = json.loads(resp1.text)
        if j['state'] != "SUCCESS":
            print("Login call - error status :" + j['state'] + '\n');
            Domoticz.Error("Login call - error status :" + j['state'] + '\n')
            raise RuntimeError("Login call - error status :" + j['state'])

        # 2nd request
        headers = {
            'Referer': 'https://sofa-connexion.grdf.fr:443/openam/oauth2/externeGrdf/authorize?response_type=code&scope=openid profile email infotravaux /v1/accreditation /v1/accreditations /digiconso/v1 /digiconso/v1/consommations new_meg /Demande.read /Demande.write&client_id=prod_espaceclient&state=0&redirect_uri=https://monespace.grdf.fr/_codexch&nonce=7cV89oGyWnw28DYdI-702Gjy9f5XdIJ_4dKE_hbsvag&by_pass_okta=1&capp=meg'
        }

        resp2 = session.get(API_BASE_URI, allow_redirects=True)
        Domoticz.Debug("2nd API Response : \n" + resp2.text)
        if resp2.status_code != requests.codes.ok:
            print("Login 2nd call - error status :" + resp2.status_code + '\n');
            Domoticz.Error("Login 2nd call - error status :" + resp2.status_code + '\n')
            raise RuntimeError("Login call - error status :" + resp2.status_code)

        return session

    def update_counters(self, start_date, end_date):
        Domoticz.Debug('start_date: ' + start_date + "; end_date: " + end_date)

        # 3nd request- Get NumPCE
        resp3 = self.session.get('https://monespace.grdf.fr/api/e-connexion/users/pce/historique-consultation')
        Domoticz.Log("Get NumPce Response : \n" + resp3.text)
        if resp3.status_code != requests.codes.ok:
            print("Get NumPce call - error status :", resp3.status_code, '\n');
            Domoticz.Error("Get NumPce call - error status :", resp3.status_code, '\n')
            exit()

        # j = json.loads(resp3.text)
        # self.pce = j[0]['numPce']

        data = self.get_data_with_interval(self.session, 'Mois', start_date, end_date)

        j = json.loads(data)
        # print (j)
        index = j[str(self.pce)]['releves'][0]['indexDebut']
        # print(index)

        for releve in j[str(self.pce)]['releves']:
            print(releve)
            req_date = releve['journeeGaziere']
            conso = releve['energieConsomme']
            volume = releve['volumeBrutConsomme']
            indexm3 = releve['indexDebut']
            try:
                index = index + conso
            except TypeError:
                print(req_date, conso, index, "Invalid Entry")
                continue

            # print(req_date, conso, index)
            self.addToDevice(float(conso), req_date)

    def get_data_with_interval(self, resource_id, start_date=None, end_date=None):
        r = self.session.get('https://monespace.grdf.fr/api/e-conso/pce/consommation/informatives?dateDebut=' + start_date + '&dateFin=' + end_date + '&pceList[]=' + str(self.pce))
        Domoticz.Debug("Data : \n" + r.text)
        if r.status_code != requests.codes.ok:
            print("Get data - error status :" + r.status_code + '\n');
            Domoticz.Error("Get data - error status :", r.status_code, '\n')
            raise RuntimeError("Get data - error status :", r.status_code, '\n')
        return r.text

    def handleConnection(self):
        try:
            if self.sConnectionStep == "idle":
                self.session = self.login()
                self.sConnectionStep = "connected"
            elif self.sConnectionStep == "connected":
                end_date = datetime.date.today()
                start_date = end_date - relativedelta(days=int(self.nb_days))
                self.update_counters(dtostr(start_date), dtostr(end_date))
                self.setNextConnection()
                self.sConnectionStep = "idle"
        except:
            pass

    def onStart(self):
        Domoticz.Debug("onStart called")
        self.username = Parameters["Mode1"]
        self.password = Parameters["Mode2"]
        self.nb_days = Parameters["Mode3"]
        self.pce = Parameters["Mode4"]

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
        Domoticz.Heartbeat(20)

    def onStop(self):
        Domoticz.Debug("onStop called")
        self.isStarted = False

    def onConnect(self, Connection, Status, Description):
        Domoticz.Debug("onConnect called")
        self.handleConnection()

    def onMessage(self, Connection, Data):
        Domoticz.Debug("onMessage called")

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Debug(
            "onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Debug("Notification: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(
            Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self, Connection):
        Domoticz.Debug("onDisconnect called")

    def onHeartbeat(self):
        Domoticz.Debug("onHeartbeat called")
        self.handleConnection()


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


def dtostr(date):
    return date.strftime("%Y-%m-%d")