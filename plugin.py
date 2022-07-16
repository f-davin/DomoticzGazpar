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
<plugin key="Gazpar" name="Compteur gaz Gazpar" author="DavTechNet" version="0.3.0" externallink="https://github.com/DavTechNet/DomoticzGazpar">
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
from datetime import date
from datetime import timedelta
from dateutil.relativedelta import relativedelta

LOGIN_BASE_URI = 'https://login.monespace.grdf.fr/sofit-account-api/api/v1/auth'
API_BASE_URI = 'https://monespace.grdf.fr/'


class BasePlugin:
    # To check that we are started, to prevent error messages when disabling or restarting the plugin
    isStarted: bool = None
    # Index of the Linky device
    iIndexUnit: int = 1
    # Name of the Linky device
    sDeviceName: str = "Gazpar"
    # string: description of the Linky device
    sDescription: str = "Compteur Gazpar"
    # integer: type (pTypeGeneral)
    iType: int = 0xF3
    # integer: subtype (sTypeManagedCounter)
    iSubType: int = 0x21
    # integer: switch type (Energy)
    iSwitchType: int = 0
    # boolean: debug mode
    iDebugLevel: bool = None
    # Username for GRDF website
    username = None
    # Password for GRDF website
    password = None
    # History to read in day
    nb_days: int = 1
    # PCE point
    pce: str = None
    # State machine
    sConnectionStep: str = None
    # Session of connection
    session = None

    def __init__(self):
        self.nextConnection = None
        self.isStarted = False
        self.sConnectionStep = "idle"
        return

    def createDevice(self):
        """
        Create Domoticz device
        """
        # Only if not already done
        if not self.iIndexUnit in Devices:
            Domoticz.Device(Name=self.sDeviceName, Unit=self.iIndexUnit, Type=self.iType, Subtype=self.iSubType,
                            Switchtype=self.iSwitchType, Description=self.sDescription, Used=1).Create()
            if not (self.iIndexUnit in Devices):
                Domoticz.Error(
                    "Ne peut ajouter le dispositif Gazpar à la base de données. Vérifiez dans les paramètres de Domoticz que l'ajout de nouveaux dispositifs est autorisé")
                return False
        return True

    def createAndAddToDevice(self, usage, Date):
        """
        Create device and insert usage in Domoticz DB
        """
        ret = False
        if self.createDevice():
            self.addToDevice(usage, Date)
            ret = True
        return ret

    def addToDevice(self, fConsumption: float, sDate: str):
        """
        Insert usage in Domoticz DB
        """
        # -1.0 for counter because Gazpar doesn't provide absolute counter value via Enedis website
        sValue = "-1.0;" + str(fConsumption * 1000) + ";" + sDate
        Devices[self.iIndexUnit].Update(nValue=0, sValue=sValue, Type=self.iType, Subtype=self.iSubType,
                                        Switchtype=self.iSwitchType)

    def updateDevice(self, usage):
        """
        Update value shown on Domoticz dashboard
        """
        if not self.createDevice():
            return False
        # -1.0 for counter because Gazpar doesn't provide absolute counter value via GRDF website
        sValue = "-1.0;" + str(usage)
        Devices[self.iIndexUnit].Update(nValue=0, sValue=sValue, Type=self.iType, Subtype=self.iSubType,
                                        Switchtype=self.iSwitchType)
        return True

    def setNextConnection(self):
        """
        Calculate next complete grab, for tomorrow between 5 and 6 am if tomorrow is true, for next hour otherwise
        """
        # Next treatment, tomorrow 6:00 pm
        # self.nextConnection = datetime.now() + timedelta(minutes=1)
        # Domoticz.Log('Next connection: ' + str(self.nextConnection))
        self.nextConnection = datetime.now() + timedelta(days=1)
        self.nextConnection = self.nextConnection.replace(hour=18)

    def login(self):
        """
        Logs the user into the GRDF API.
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
            'Referer': 'https://login.monespace.grdf.fr/mire/connexion?goto=https:%2F%2Fsofa-connexion.grdf.fr:443%2Fopenam%2Foauth2%2FexterneGrdf%2Fauthorize%3Fresponse_type%3Dcode%26scope%3Dopenid%2520profile%2520email%2520infotravaux%2520%252Fv1%252Faccreditation%2520%252Fv1%252Faccreditations%2520%252Fdigiconso%252Fv1%2520%252Fdigiconso%252Fv1%252Fconsommations%2520new_meg%2520%252FDemande.read%2520%252FDemande.write%26client_id%3Dprod_espaceclient%26state%3D0%26redirect_uri%3Dhttps%253A%252F%252Fmonespace.grdf.fr%252F_codexch%26nonce%3D7cV89oGyWnw28DYdI-702Gjy9f5XdIJ_4dKE_hbsvag%26by_pass_okta%3D1%26capp%3Dmeg&realm=%2FexterneGrdf&capp=meg',
            'domain': 'grdf.fr'
        }

        resp1 = session.post(LOGIN_BASE_URI, data=payload, headers=headers)
        # Domoticz.Debug("1st Auth Response : \n" + resp1.text)
        if resp1.status_code != requests.codes.ok:
            Domoticz.Error("Login call - error status :" + str(resp1.status_code) + '\n')
            raise RuntimeError("Login call - error status :" + str(resp1.status_code))

        j = json.loads(resp1.text)
        if j['state'] != "SUCCESS":
            Domoticz.Error("Login call - error status :" + j['state'] + '\n')
            raise RuntimeError("Login call - error status :" + j['state'])

        # 2nd request
        headers = {
            'Referer': 'https://sofa-connexion.grdf.fr:443/openam/oauth2/externeGrdf/authorize?response_type=code&scope=openid profile email infotravaux /v1/accreditation /v1/accreditations /digiconso/v1 /digiconso/v1/consommations new_meg /Demande.read /Demande.write&client_id=prod_espaceclient&state=0&redirect_uri=https://monespace.grdf.fr/_codexch&nonce=7cV89oGyWnw28DYdI-702Gjy9f5XdIJ_4dKE_hbsvag&by_pass_okta=1&capp=meg'
        }

        resp2 = session.get(API_BASE_URI, allow_redirects=True)
        # Domoticz.Debug("2nd API Response : \n" + resp2.text)
        if resp2.status_code != requests.codes.ok:
            Domoticz.Error("Login 2nd call - error status :" + str(resp2.status_code) + '\n')
            raise RuntimeError("Login call - error status :" + str(resp2.status_code))

        return session

    def update_counters(self, start_date, end_date):
        Domoticz.Debug('start_date: ' + start_date + "; end_date: " + end_date)

        # 3nd request- Get NumPCE
        # resp3 = self.session.get('https://monespace.grdf.fr/api/e-connexion/users/pce/historique-consultation')
        # Domoticz.Log("Get NumPce Response : \n" + resp3.text)
        # if resp3.status_code != requests.codes.ok:
        #     Domoticz.Error("Get NumPce call - error status :", str(resp3.status_code), '\n')
        #     exit()

        # j = json.loads(resp3.text)
        # self.pce = j[0]['numPce']

        data = self.get_data_with_interval('Mois', start_date, end_date)

        j = json.loads(data)
        index = j[str(self.pce)]['releves'][0]['indexDebut']

        for releve in j[str(self.pce)]['releves']:
            Domoticz.Debug(releve)
            req_date = releve['journeeGaziere']
            Domoticz.Debug("req_date: " + str(req_date))
            conso = releve['energieConsomme']
            Domoticz.Debug("energieConsomme: " + str(conso))
            # volume = releve['volumeBrutConsomme']
            # indexm3 = releve['indexDebut']
            # try:
            #     index = index + conso
            # except TypeError:
            #     Domoticz.Error(req_date, conso, index, "Invalid Entry")
            #     continue

            # if conso is not None:
            self.addToDevice(conso, str(req_date))

    def get_data_with_interval(self, resource_id, start_date=None, end_date=None):
        r = self.session.get(
            'https://monespace.grdf.fr/api/e-conso/pce/consommation/informatives?dateDebut=' + start_date + '&dateFin=' + end_date + '&pceList[]=' + str(
                self.pce))
        # Domoticz.Debug("Data : \n" + r.text)
        if r.status_code != requests.codes.ok:
            Domoticz.Error("Get data - error status :", r.status_code, '\n')
            raise RuntimeError("Get data - error status :", r.status_code, '\n')
        return r.text

    def handleConnection(self):
        if datetime.now() > self.nextConnection:
            try:
                # Domoticz.Debug("Current state: ", str(self.sConnectionStep))
                if self.sConnectionStep == "idle":
                    self.session = self.login()
                    # Domoticz.Debug("Login success")
                    self.sConnectionStep = "connected"
                elif self.sConnectionStep == "connected":
                    end_date = date.today()
                    start_date = end_date - relativedelta(days=int(self.nb_days))
                    # Domoticz.Debug("Start date: ", str(start_date), "\tEnd date: ", str(end_date))
                    self.update_counters(dtostr(start_date), dtostr(end_date))
                    # Domoticz.Debug("Counter updated")
                    self.setNextConnection()
                    # Domoticz.Debug("Next connection setted")
                    self.sConnectionStep = "idle"
                else:
                    Domoticz.Error("Wrong connection step: state = ", str(self.sConnectionStep),
                                   ". Reset state to idle")
                    self.sConnectionStep = "idle"
            except:
                Domoticz.Error("Error during connection or reading values: state %1", str(self.sConnectionStep))
                self.sConnectionStep = "idle"

    def onStart(self):
        Domoticz.Debug("onStart called")
        self.username = Parameters["Mode1"]
        self.password = Parameters["Mode2"]
        self.nb_days = Parameters["Mode3"]
        self.pce = Parameters["Mode4"]

        if Parameters["Mode6"] == "Debug":
            Domoticz.Debugging(1)
            # Domoticz.Log("Debugger started, use 'telnet 0.0.0.0 4444' to connect")
            # import rpdb
            # rpdb.set_trace()

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
