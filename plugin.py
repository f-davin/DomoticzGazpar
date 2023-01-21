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
<plugin key="Gazpar" name="Compteur gaz Gazpar" author="DavTechNet" version="0.3.1" externallink="https://github.com/DavTechNet/DomoticzGazpar">
    <description>
        <h2>Gazpar plugin</h2><br/>
        This plugin permits the get the gas consummation information from the GRDF website.
        Based on https://github.com/Scrat95220/DomoticzGazpar.git.
        <h3>Configuration</h3>
        Enter the following information to configure the plugin:
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

import json
from datetime import date
from datetime import datetime
from datetime import timedelta
from enum import Enum, unique

import Domoticz
import requests
from dateutil.relativedelta import relativedelta

LOGIN_BASE_URI = 'https://login.monespace.grdf.fr/sofit-account-api/api/v1/auth'
API_USER_URI = 'https://monespace.grdf.fr/api/e-connexion/users/whoami'
AUTH_NONE_URI = 'https://monespace.grdf.fr/client/particulier/accueil'
DELAY_BETWEEN_REQUESTS = 1  # Delay in seconds


@unique
class LogLevel ( Enum ):
    """
    Enumeration of the different log levels
    """
    Notice = 0
    Error = 1
    Debug = 2


class BasePlugin:
    # To check that we are started, to prevent error messages when disabling or restarting the plugin
    is_started: bool = None
    # Index of the Linky device
    index_unit: int = 1
    # Name of the Linky device
    device_name: str = "Gazpar"
    # string: description of the Linky device
    description: str = "Compteur Gazpar"
    # integer: type (pTypeGeneral)
    type: int = 0xF3
    # integer: subtype (sTypeManagedCounter)
    sub_type: int = 0x21
    # integer: switch type (Energy)
    switch_type: int = 0

    def __init__ ( self ):
        self.username: str = None  # Username for GRDF website
        self.password: str = None  # Password for GRDF website
        self.nb_days: int = 1  # History to read in day
        self.next_connection: datetime = None
        self.is_started: bool = False
        self.connection_step: str = "idle"  # Default connection step
        self.session: requests.Session = None
        self.pce: str = None

    def createDevice ( self ):
        """
        Create Domoticz device
        """
        # Only if not already done
        if not self.index_unit in Devices:
            Domoticz.Device ( Name = self.device_name, Unit = self.index_unit, Type = self.type,
                              Subtype = self.sub_type,
                              Switchtype = self.switch_type, Description = self.description, Used = 1
                              ).Create ( )
            if not (self.index_unit in Devices):
                log_message ( LogLevel.Error,
                              "Ne peut ajouter le dispositif Gazpar à la base de données. Vérifiez dans les paramètres de Domoticz que l'ajout de nouveaux dispositifs est autorisé"
                              )
                return False
        return True

    def createAndAddToDevice ( self, usage, Date ):
        """
        Create device and insert usage in Domoticz DB
        """
        ret = False
        if self.createDevice ( ):
            self.addToDevice ( usage, Date )
            ret = True
        return ret

    def addToDevice ( self, fConsumption: float, sDate: str ):
        """
        Insert usage in Domoticz DB
        """
        # -1.0 for counter because Gazpar doesn't provide absolute counter value via Enedis website
        sValue = "-1.0;" + str ( fConsumption * 1000 ) + ";" + sDate
        Devices [ self.index_unit ].Update ( nValue = 0, sValue = sValue, Type = self.type, Subtype = self.sub_type,
                                             Switchtype = self.switch_type
                                             )

    def updateDevice ( self, usage ):
        """
        Update value shown on Domoticz dashboard
        """
        if not self.createDevice ( ):
            return False
        # -1.0 for counter because Gazpar doesn't provide absolute counter value via GRDF website
        sValue = "-1.0;" + str ( usage )
        Devices [ self.index_unit ].Update ( nValue = 0, sValue = sValue, Type = self.type, Subtype = self.sub_type,
                                             Switchtype = self.switch_type
                                             )
        return True

    def set_next_connection ( self ):
        """
        Calculate next complete grab, for tomorrow between 5 and 6 am if tomorrow is true, for next hour otherwise
        """
        # Next treatment, tomorrow 6:00 pm
        self.next_connection = datetime.now ( ) + timedelta ( minutes = 1 )
        log_message ( LogLevel.Notice, 'Next connection: ' + str ( self.next_connection ) )
        # self.next_connection = datetime.now() + timedelta(days=1)
        # self.next_connection = self.next_connection.replace(hour=18)

    def login ( self ):
        """
        Logs the user into the GRDF API.
        """
        session = requests.Session ( )

        # Get cookie
        req = session.get ( AUTH_NONE_URI )
        if not 'auth_nonce' in session.cookies:
            log_message ( LogLevel.Error, 'Cannot get auth_nonce.' )
        else:
            log_message ( LogLevel.Debug, 'Cookies ok.' )

        auth_nonce = self.session.cookies.get ( 'auth_nonce' )
        log_message ( LogLevel.Debug, "auth_nonce: " + auth_nonce )

        payload = {
            'email'   : self.username,
            'password': self.password,
            'goto'    : 'https://sofa-connexion.grdf.fr:443/openam/oauth2/externeGrdf/authorize',
            'capp'    : 'meg'
            }
        headers = {
            'Content-Type'   : 'application/x-www-form-urlencoded; charset=UTF-8',
            # 'Referer'        : 'https://login.monespace.grdf.fr/mire/connexion?goto=https:%2F%2Fsofa-connexion.grdf.fr:443%2Fopenam%2Foauth2%2FexterneGrdf%2Fauthorize%3Fresponse_type%3Dcode%26scope%3Dopenid%2520profile%2520email%2520infotravaux%2520%252Fv1%252Faccreditation%2520%252Fv1%252Faccreditations%2520%252Fdigiconso%252Fv1%2520%252Fdigiconso%252Fv1%252Fconsommations%2520new_meg%2520%252FDemande.read%2520%252FDemande.write%26client_id%3Dprod_espaceclient%26state%3D0%26redirect_uri%3Dhttps%253A%252F%252Fmonespace.grdf.fr%252F_codexch%26nonce%3D7cV89oGyWnw28DYdI-702Gjy9f5XdIJ_4dKE_hbsvag%26by_pass_okta%3D1%26capp%3Dmeg&realm=%2FexterneGrdf&capp=meg',
            'domain'         : 'grdf.fr',
            'User-Agent'     : 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/99.0.4844.0 Safari/537.36',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept'         : 'application/json, */*',
            'Connection'     : 'keep-alive'
            }

        # Login request
        response = session.post ( LOGIN_BASE_URI, data = payload, headers = headers, allow_redirects = False )
        log_message ( LogLevel.Debug, "First Auth Response : \n" + response.text )
        status_code = str ( response.status_code )
        if response.status_code != requests.codes.ok:
            error = ''
            if response.status_code >= 500:
                error = 'client error (code: {0}'.format ( status_code )
            else:
                error = 'server error (code: {0}'.format ( status_code )
            log_message ( LogLevel.Error, "First login request - " + error + '\n' )
            raise RuntimeError ( "First login request - " + error )
        else:
            log_message ( LogLevel.Debug, "Status code of first request: " + status_code )

        json_content = json.loads ( response.text )
        if json_content [ 'state' ] != "SUCCESS":
            if json_content [ 'error' ] == "AUTH_FAIL":
                error = 'Authentication failed, server response: {0}'.format ( json_content [ 'message' ] )
            elif json_content [ 'error' ] == "LOGIN_INVALID_ATTEMPS":
                error = 'Tentative number is too important, server response: {0}'.format ( json_content [ 'message' ] )
            elif json_content [ 'error' ] == "CAPTCHA_FAIL":
                error = 'Authentication failed because captcha is invalid, server response: {0}'.format (
                    json_content [ 'message' ]
                    )
            else:
                error = 'Unexpected error, server message: {0}'.format ( json_content [ 'message' ] )
            log_message ( LogLevel.Error, 'An error occurs during login: \n\t' + error + '\n' )
            raise RuntimeError ( 'An error occurs during login: ' + error )

        # Complete login by call whoami
        response = session.get ( API_USER_URI, allow_redirects = True )
        log_message ( LogLevel.Debug, "Whoami response : \n" + response.text )
        if response.status_code != requests.codes.ok:
            error = ''
            if response.status_code >= 500:
                error = 'client error (code: {0}'.format ( status_code )
            else:
                error = 'server error (code: {0}'.format ( status_code )
            log_message ( LogLevel.Error, "Whoami request - " + error + '\n' )
            raise RuntimeError ( "Whoami request - " + error )
        else:
            log_message ( LogLevel.Debug, "Session opened with success" )

        return session

    def update_counters ( self, start_date: str, end_date: str ):
        log_message ( LogLevel.Debug, 'start_date: ' + start_date + "; end_date: " + end_date )

        data = self.get_data_with_interval ( 'Mois', start_date, end_date )

        j = json.loads ( data )
        index = j [ str ( self.pce ) ] [ 'releves' ] [ 0 ] [ 'indexDebut' ]

        for releve in j [ str ( self.pce ) ] [ 'releves' ]:
            log_message ( LogLevel.Debug, releve )
            req_date = releve [ 'journeeGaziere' ]
            log_message ( LogLevel.Debug, "req_date: " + str ( req_date ) )
            conso = releve [ 'energieConsomme' ]
            log_message ( LogLevel.Debug, "energieConsomme: " + str ( conso ) )

            self.addToDevice ( conso, str ( req_date ) )

    def get_data_with_interval ( self, resource_id, start_date: str = None, end_date: str = None ):
        r = self.session.get (
            'https://monespace.grdf.fr/api/e-conso/pce/consommation/informatives?dateDebut=' + start_date + '&dateFin=' + end_date + '&pceList[]=' + self.pce
            # 'https://monespace.grdf.fr/api/e-conso/pce/consommation/publiees?dateDebut=' + start_date + '&dateFin=' + end_date + '&pceList[]=' + self.pce
            )
        log_message ( LogLevel.Debug, "Data : \n" + r.text )
        if r.status_code != requests.codes.ok:
            log_message ( LogLevel.Error, "Get data - error status : {0}\n".format ( str ( r.status_code ) ) )
            raise RuntimeError ( "Get data - error status : {0}".format ( str ( r.status_code ) ) )
        return r.text

    def handle_connection ( self ):
        if datetime.now ( ) > self.next_connection:
            try:
                log_message ( LogLevel.Debug, "Current state: {0}".format ( self.connection_step ) )
                if self.connection_step == "idle":
                    self.session = self.login ( )
                    log_message ( LogLevel.Debug, "Login success" )
                    self.connection_step = "connected"
                elif self.connection_step == "connected":
                    end_date = date.today ( )
                    start_date = end_date - relativedelta ( days = int ( self.nb_days ) )
                    log_message ( LogLevel.Debug,
                                  "Start date: {0}\tEnd date: {1}".format ( str ( start_date ), str ( end_date ) )
                                  )
                    self.update_counters ( date_to_string ( start_date ), date_to_string ( end_date ) )
                    log_message ( LogLevel.Debug, "Counter updated" )
                    self.set_next_connection ( )
                    log_message ( LogLevel.Debug, "Next connection set" )
                    self.connection_step = "idle"
                else:
                    log_message ( LogLevel.Error, "Wrong connection step: state = {0}. Reset state to idle".format (
                        self.connection_step
                        )
                                  )
                    self.connection_step = "idle"
            except:
                log_message ( LogLevel.Error,
                              "Error during connection or reading values: state {0}".format ( self.connection_step )
                              )
                self.connection_step = "idle"

    def onStart ( self ):
        log_message ( LogLevel.Debug, "onStart called" )
        self.username = Parameters [ "Mode1" ]
        self.password = Parameters [ "Mode2" ]
        self.nb_days = Parameters [ "Mode3" ]
        self.pce = Parameters [ "Mode4" ]

        if Parameters [ "Mode6" ] == "Debug":
            Domoticz.Debugging ( 1 )
            # log_message ( LogLevel.Debug, "Debugger started, use 'telnet 0.0.0.0 4444' to connect" )
            # import rpdb
            # rpdb.set_trace()

        if self.createDevice ( ):
            self.next_connection = datetime.now ( )
        else:
            self.set_next_connection ( )

        # Now we can enabling the plugin
        self.is_started = True
        Domoticz.Heartbeat ( 20 )

    def onStop ( self ):
        log_message ( LogLevel.Debug, "onStop called" )
        self.is_started = False

    def onConnect ( self, Connection, Status, Description ):
        log_message ( LogLevel.Debug, "onConnect called" )

    def onMessage ( self, Connection, Data ):
        log_message ( LogLevel.Debug, "onMessage called" )

    def onCommand ( self, Unit, Command, Level, Hue ):
        log_message ( LogLevel.Debug,
                      "onCommand called for Unit " + str ( Unit ) + ": Parameter '" + str ( Command
                                                                                            ) + "', Level: " + str (
                          Level
                          )
                      )

    def onNotification ( self, Name, Subject, Text, Status, Priority, Sound, ImageFile ):
        log_message ( LogLevel.Debug, "Notification: " + Name + "," + Subject + "," + Text + "," + Status + "," + str (
            Priority
            ) + "," + Sound + "," + ImageFile
                      )

    def onDisconnect ( self, Connection ):
        log_message ( LogLevel.Debug, "onDisconnect called" )

    def onHeartbeat ( self ):
        log_message ( LogLevel.Debug, "onHeartbeat called" )
        self.handle_connection ( )


global _plugin
_plugin = BasePlugin ( )


def onStart ( ):
    global _plugin
    _plugin.onStart ( )


def onStop ( ):
    global _plugin
    _plugin.onStop ( )


def onConnect ( Connection, Status, Description ):
    global _plugin
    _plugin.onConnect ( Connection, Status, Description )


def onMessage ( Connection, Data ):
    global _plugin
    _plugin.onMessage ( Connection, Data )


def onCommand ( Unit, Command, Level, Hue ):
    global _plugin
    _plugin.onCommand ( Unit, Command, Level, Hue )


def onNotification ( Name, Subject, Text, Status, Priority, Sound, ImageFile ):
    global _plugin
    _plugin.onNotification ( Name, Subject, Text, Status, Priority, Sound, ImageFile )


def onDisconnect ( Connection ):
    global _plugin
    _plugin.onDisconnect ( Connection )


def onHeartbeat ( ):
    global _plugin
    _plugin.onHeartbeat ( )


# Generic helper functions
def date_to_string ( value: date ) -> str:
    """
    Convert a date to string
    :param value: Date to convert
    :return: Date converted at format YYYY-MM-DD
    """
    return value.strftime ( "%Y-%m-%d" )


def log_message ( level: LogLevel, message: str ):
    """
    Add a message in the log
    :param level: Level of the message to log
    :param message: Message to log
    :return: Nothing
    """
    if level == LogLevel.Debug:
        Domoticz.Debug ( message )
    elif level == LogLevel.Error:
        Domoticz.Error ( message )
    elif level == LogLevel.Notice:
        Domoticz.Log ( message )
