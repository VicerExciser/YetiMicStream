### sensors/cnc_base/alcazar_common/cnc/cnc_base.py

"""A module that contains a base class for Alcazar sensors plus supporting
code and tests.
"""

import datetime
import fcntl
import socket
import struct
import sys
import threading
import typing
import uuid
import time
import logging
import os
import signal

from .. import config, logger
from ..models import telem_message as model
from .presentation_layer import KafkaPresentationLayer
from . import serializer


def get_default_iface_name_linux():
    """
    Return the default interface name of the device hosting the CNC class.
    Needed to differentiate NUCs from Pis.
    https://stackoverflow.com/questions/20908287/is-there-a-method
    """
    route = "/proc/net/route"
    with open(route) as f:
        for line in f.readlines():
            try:
                iface, dest, _, flags, _, _, _, _, _, _, _, = line.strip().split()
                if dest != '00000000' or not int(flags, 16) & 2:
                    continue
                return iface
            except:
                continue


class UnknownMessageTypeException(Exception):
    def __init__(self, message):
        pass
        # Should I implement a __str__ method or something?


class CNCBase:
    """
    A base class for Alcazar sensors / bots.
    """

    def __init__(self, component_site: str, component_type: str,
                 topics: typing.Union[str, typing.List[str]], component_id: str = None,
                 component_friendly_name: str = None, config_file: str = None,
                 heartbeat_period: int = 30, component_name: str = None):
        """
        Construct a new CNCBase object. Subclasses can use the send_* family of
        methods to send data to the Kafka server. The handle_message method
        should be overridden to handle callbacks from Kafka when a new message
        is received. The start method can be called to begin processing Kafka
        messages.

        :param component_site: The site of the component sending the message.
        :param component_type: The type of this object. One of
            telem_message.ComponentTypes.
        :param topics: The topic(s) to subscribe to in Kafka. It is either a single string or a
            list of strings. The string(s) can be a regex, like 'CNC.Control.*'
        :param component_id: The ID number for a given node or component. If
            None, default to the MAC address.
        :param component_friendly_name: An optional human-readable name for
            this component.
        :param config_file: The path to the configuration file for this node.
            If None, use the default configuration values.
        :param heartbeat_period: The time between each heartbeat (in seconds).
        :param component_name: The name of a component to be used in the topic of sent messages. If
            none, use the friendly name.
        """
        self.__state = ''
        self.version = '0.1'
        self.commander_id = 'commander'
        self.component_site = component_site
        self.topics = topics
        self.component_type = component_type
        self.config = config.read_config(config_file)

        logging.getLogger('kafka').setLevel(logging.CRITICAL)

        if component_id is not None:
            self.component_id = component_id
        else:
            try:
                self.component_id = self.config.get('node', 'virtualnodeid')
                if self.component_id == '':
                    raise AssertionError
            except Exception:
                self.component_id = self._get_mac_address()
        if component_friendly_name is not None:
            self.component_friendly_name = component_friendly_name
        else:
            self.component_friendly_name = self.component_id
        if component_name is not None:
            self.component_name = component_name
        else:
            self.component_name = self.component_friendly_name
        self.component_name = self.component_name.replace(' ', '_')
        self.heartbeat_period = heartbeat_period
        self.logger = logger.get_logger('cnc_base')

        self.kafka_server = '{}:{}'.format(
            self.config.get('kafka', 'hostname'),
            self.config.get('kafka', 'port'),
        )

        # Instantiate the serializer
        self.serializer = serializer.JSONSerializer()

        # This is used to determine the status sent in the heartbeat.  Sensors
        # should use the set_ready method to change this.
        self.ready = False
        self.presentation_layer = None

        # This is used to stop the heartbeat thread
        self.heart_should_beat = True
        self.heartbeat_event = threading.Event()
        self.heartbeat_event.clear()  # wait method will wait until flag is set

        self.heartbeat_thread = threading.Thread(target=self.heartbeat_thread)
        self.logger.debug('CNC Base listening on {}'.format(self.topics))

    @property
    def running(self):
        return self.heart_should_beat

    def update_state(self, new_state):
        """
        Update the state variable to the provided string. This will be sent in
        all heartbeats.

        :param new_state: The new string to use as the device's current state.
        """
        self.__state = new_state

    def start(self):
        """Starts the heartbeat and starts listening for messages.

        Should be called after construction.
        """
        # Start listening for messages
        self.connect_to_presentation()

        # Start the heartbeat
        self.heartbeat_thread.start()

    def shutdown(self):
        """Call this when it's time to clean up all resources consumed by this
        bot.
        """
        # Shutdown the presentation layer
        if self.presentation_layer is not None:
            self.presentation_layer.shutdown()

        # Shutdown the heartbeat thread
        self.heart_should_beat = False
        self.heartbeat_event.set()  # wake up!
        self.heartbeat_thread.join()

    def set_ready(self, ready):
        """Child classes should call this when the sensor is actually starting
        to send data, or when the sensor is no longer ready.
        """

        if ready != self.ready:
            self.ready = ready
            self.send_heartbeat()  # because ready has changed

    def connect_to_presentation(self):
        self.logger.info(f'Connecting to kafka at {self.kafka_server}')
        if self.presentation_layer is not None:
            self.presentation_layer.shutdown()

        for i in range(self.config.getint('kafka', 'max_retries')):
            try:
                self.presentation_layer = KafkaPresentationLayer(
                    server=[self.kafka_server],
                    serializer=self.serializer.serialize_to_utf_8,
                    deserializer=self.serializer.deserialize_from_utf_8,
                    group_id=self.component_id
                )
                self.presentation_layer.start(self.topics, cb_func=self.handle_message)
                break
            except Exception as e:
                self.logger.warning(f'Unable to connect to Kafka because {e}, retrying...')
                time.sleep(self.config.getint('kafka', 'retry_wait_time'))
        else:
            self.logger.warning('Heartbeat thread stopping because could not reach Kafka')

            # We want to shutdown the cleanly here. But python-kafka has no mechanism to wake up a
            # consumer when Kafka goes down. So instead we have to nuke everything.  These sensors
            # are expected to be running in a docker container, so it's okay.
            os.kill(os.getpid(), signal.SIGKILL)

    def heartbeat_thread(self):
        """A thread function to send a heartbeat at an appropriate interval.

        Each bot has its own heartbeat.
        """
        while self.heart_should_beat:
            # set the bot's heartbeat event to end the wait immediately
            self.send_heartbeat()
            self.heartbeat_event.wait(timeout=self.heartbeat_period)

    def get_topic_string(self, msg_type: str, msg_subtype: str,
                         component_name: typing.Optional[str] = None,
                         component_site: typing.Optional[str] = None):
        """
        Get the kafka topic string for a message.

        :param msg_type: The message type to be included in the topic string.
        :param msg_subtype: The message subtype to be included in the topic string.
        :param component_name: If specified, override the component name of the instance in the
            topic.
        :param component_site: If specified, override the component site of the instance in the
            topic.
        """
        component_name = component_name if component_name is not None else self.component_name
        component_site = component_site if component_site is not None else self.component_site
        return '{}.{}.{}.{}.{}'.format(
            model.CNC_STRING, msg_type, msg_subtype, component_name, component_site
        )

    def send_message(self, recipient: str, message_type: str,
                     message_subtype: str, message_body: dict):
        """
        Send a message to the commander via the underlying presentation layer.

        :param recipient: The recipient topic of the message.
        :param message_type: The type of the message. One of
            telem_message.MessageTypes.
        :param message_subtype: The subtype of the message.
        :param message_body: The body of the message. Must match the
            message_type.
        """
        msg = {
            'version': self.version,
            'componentId': self.component_id,
            'componentType': self.component_type,
            'componentSite': self.component_site,
            'componentFriendlyName': self.component_friendly_name,
            'messageTimestamp': self._get_timestamp(),
            'messageId': str(uuid.uuid4()),
            'messageType': message_type,
            'messageSubtype': message_subtype,
            'messageBody': message_body,
        }
        self.logger.debug('Sending to {} message {}'.format(recipient, msg))
        if self.presentation_layer is None:
            self.logger.warning(
                'Unable to send message, not connected to Kafka, attempting to reconnect')
            self.connect_to_presentation()
            if self.presentation_layer is None:
                self.logger.error('Unable to reconnect to kafka, dropping message')
                return

        try:
            self.presentation_layer.send_message(msg, recipient)
        except Exception as e:
            self.logger.warning(f'Error sending message {e}')
            self.connect_to_presentation()

    def send_raw(self, title: str, details: dict,
                 subtype: str = model.RawMessageSubtypes.Data.value,
                         component_name: typing.Optional[str] = None,
                         component_site: typing.Optional[str] = None):
        """
        Send a raw message to Kafka

        :param title: The title of the raw message.
        :param details: The details of the raw message.
        :param subtype: The subtype of the raw message.
        :param component_name: If specified, override the component name of the instance in the
            topic.
        :param component_site: If specified, override the component site of the instance in the
            topic.
        """
        msg_body = {
            'rawTitle': title,
            'rawDetail': details,
        }
        msg_type = model.MessageTypes.Raw.value
        recipient = self.get_topic_string(msg_type, subtype, component_name, component_site)
        self.send_message(recipient, msg_type, subtype, msg_body)

    def send_raw_dict(
            self, body: dict,
            sensor: model.RawMessageSubtypes = model.RawMessageSubtypes.Data,
            component_name: typing.Optional[str] = None,
            component_site: typing.Optional[str] = None):
        """
        Send a raw message to Kafka

        :param body: The body of the raw message.
        :param sensor: The sensor/component sending the raw message.
        :param component_name: If specified, override the component name of the instance in the
            topic.
        :param component_site: If specified, override the component site of the instance in the
            topic.
        """
        msg_type = model.MessageTypes.Raw.value
        recipient = self.get_topic_string(msg_type, sensor, component_name, component_site)
        self.send_message(recipient, msg_type, sensor.value, body)

    def send_alert(self, subtype: str, severity: int, confidence: int,
                   title: str, text: str, details: dict = None,
                   message_refs: typing.List[str] = None,
                   component_name: typing.Optional[str] = None,
                   component_site: typing.Optional[str] = None):
        """
        Send an alert message to Kafka.

        :param subtype: The subtype of the alert message. One of
            telem_message.AlertMessageSubtypes.
        :param severity: An integer corresponding to model.SeverityTypes.
        :param confidence: A confidence score in the range [1, 6].
        :param title: An alert title.
        :param text: The alert text.
        :param details: An optional dictionary of additional alert details.
        :param message_refs: An optional list of related messageIds.
        :param component_name: If specified, override the component name of the instance in the
            topic.
        :param component_site: If specified, override the component site of the instance in the
            topic.
        """
        if message_refs is None:
            message_refs = []
        if details is None:
            details = {}
        msg_body = {
            'severity': severity,
            'confidence': confidence,
            'host': socket.gethostname(),
            'messageRef': message_refs,
            'alertTitle': title,
            'alertText': text,
            'alertDetail': details,
        }
        msg_type = model.MessageTypes.Alert.value
        recipient = self.get_topic_string(msg_type, subtype, component_name, component_site)
        self.send_message(recipient, msg_type, subtype, msg_body)

    def send_control(self, target: str, subtype: str, title: str, text: str,
                     detail: typing.Dict = None,
                     component_name: typing.Optional[str] = None,
                     component_site: typing.Optional[str] = None):
        """
        Send a control message to Kafka.

        :param target: The target ID of this command.
        :param subtype: The subtype of the command. One of
            telem_message.ControlMessageSubtypes.
        :param title: The command title.
        :param text: The comand text.
        :param detail: An optional dictionary of additional command details.
        :param component_name: If specified, override the component name of the instance in the
            topic.
        :param component_site: If specified, override the component site of the instance in the
            topic.
        """
        if detail is None:
            detail = {}
        msg_body = {
            'target': target,
            'commandTitle': title,
            'commandText': text,
            'commandDetail': detail,
        }
        recipient = self.get_topic_string(model.MessageTypes.Control.value, subtype,
                                          component_name, component_site)
        self.send_message(recipient, model.MessageTypes.Control.value,
                          subtype, msg_body)

    def send_heartbeat(self):
        """Sends a heartbeat.  This base class will normally take care of
        heartbeats, though children may call this if they really want to send
        an extra heartbeat.

        Remember that this method may be called at indeterminate times from
        different threads.
        """
        self.send_control(
            self.commander_id, model.ControlMessageSubtypes.Heartbeat.value,
            'heartbeat', self.__state,
        )

    @staticmethod
    def _get_timestamp():
        """
        Return the timestamp formatted correctly as per the ICD.
        """
        return '{}Z'.format(
            datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]
        )

    @staticmethod
    def _get_mac_address():
        """
        Return the MAC address of the default interface. Platform-specific
        hack for Linux per
        https://stackoverflow.com/questions/159137/getting-mac-address
        """
        if not sys.platform.startswith('linux'):
            raise RuntimeError(
                'Cannot get the MAC address on non-Linux platforms'
            )
        ifname = get_default_iface_name_linux()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        info = fcntl.ioctl(s.fileno(), 0x8927,
                           struct.pack('256s', bytes(ifname, 'utf-8')[:15]))
        return ''.join('%02x' % b for b in info[18:24])

    def handle_message(self, validated_message: dict):
        """
        The callback for when a message is received on the listening topic.
        """
        pass


class SensorBase(CNCBase):
    def __init__(self, component_site: str, component_type: str, component_name: str,
                 topics: str, component_id: str = None,
                 component_friendly_name: str = None, config_file: str = None,
                 heartbeat_period: int = 30):
        super().__init__(component_site, component_type, topics, component_id,
                         component_friendly_name, config_file, heartbeat_period,
                         component_name
                         )
        self.message_handler_table = {}
        self.add_message_callback(
            model.ControlMessageSubtypes.Config.value, self.do_config)
        self.add_message_callback(
            model.ControlMessageSubtypes.Reboot.value, self.do_reboot)
        self.add_message_callback(
            model.ControlMessageSubtypes.Refresh.value, self.do_refresh)
        self.add_message_callback(
            model.ControlMessageSubtypes.Activate.value, self.do_activate)
        self.add_message_callback(
            model.ControlMessageSubtypes.Deactivate.value, self.do_deactivate)

    def add_message_callback(self, subtype: str,
                             callback: typing.Callable[[typing.Dict], None]):
        """
        Subscribe to a given Kafka subtype.

        :param subtype: The Kafka subtype to subscribe to.
        :param callback: The callback function that will be called.
            The callback function takes a single parameter, which should
            be the validated message dictionary.
        """
        self.message_handler_table[subtype] = callback

    def handle_message(self, validated_message: dict):
        """
        Call this when a message is received from the presentation layer.

        The presentation layer should handle validation.

        :param validated_message: The validated message. Should conform to
            telem_models.Message.
        """
        self.logger.debug(f'Sensor received message {validated_message}')
        if (validated_message['messageType'] !=
                model.MessageTypes.Control.value):
            self.logger.debug(
                'Sensor ignoring because messageType was not control'
            )
            return
        if validated_message['messageBody']['target'] != self.component_id:
            self.logger.debug(
                'Sensor ignoring because not targeted at me'
            )
            return

        subtype = validated_message['messageSubtype']
        try:
            self.logger.debug(f'Dispatching message with subtype {subtype}')
            self.message_handler_table[subtype](validated_message)
        except KeyError:
            self.logger.warning(f'No handler for with subtype {subtype}')
            pass

    def do_config(self, validated_message):
        """Used to set the configuration of the sensor.
        """
        raise NotImplementedError()  # implement in child

    def do_reboot(self, validated_message):
        """Used to reboot the sensor.
        """
        raise NotImplementedError()  # implement in child

    def do_refresh(self, validated_message):
        """Used to reset the sensor's state.

        What's the difference between this and reboot?
        """
        raise NotImplementedError()  # implement in child

    def do_activate(self, validated_message):
        """Activate the sensor to cause it to start collecting and sending
        data.
        """
        raise NotImplementedError()  # implement in child

    def do_deactivate(self, validated_message):
        """Deactivate the sensor.

        A deactivated sensor should not publish data.
        """
        raise NotImplementedError()  # implement in child


class SensorUtil:
    @staticmethod
    def main_loop(on_activate_cb, sensor_class, *sensor_args):
        while True:
            sensor = None
            try:
                sensor = sensor_class(*sensor_args)
                sensor.start()
                sensor.my_logger.info(
                    f'MAC is: {SensorBase._get_mac_address()}'
                )
                sensor.do_activate('Activation call')
                on_activate_cb(sensor)
            except KeyboardInterrupt:
                if sensor is not None:
                    sensor.do_deactivate('Deactivation call')
                    sensor.shutdown()
                sys.exit(0)
            except Exception as exc:
                print(exc)
