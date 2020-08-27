### sensors/cnc_base/alcazar_common/models/telem_message.py

"""
This module describes a data model for telemetry network messages.

The model is built on the document entitled LAVA+ Message ICD written by APL,
version 0.1.  APL and GTRI are still coming together on the final version of
this model, but since GTRI is mostly concerned with CONTROL type messages,
this model's completion trajectory focuses on those.
"""

from dataclasses import field
import enum
import datetime
from typing import List

from marshmallow.decorators import validates_schema
from marshmallow.exceptions import ValidationError
from marshmallow import fields
from marshmallow.validate import OneOf, Length, Range, Regexp, Equal
from marshmallow_dataclass import dataclass


VERSION = 0.1  # This is the current version of the ICD and of this model
CNC_STRING = 'CNC'


def validate_datetimestamp(value):
    datetime.datetime.strptime(value, '%Y-%m-%dT%H:%M:%S.%fZ')
    return True


class FieldEnumeration(enum.Enum):
    @classmethod
    def values(cls):
        return [field.value for field in cls]

    def __str__(self):
        # allows us to serialize by value, as the spec expects
        return self.value


class ComponentTypes(FieldEnumeration):
    Commander = 'COMMANDER'
    Sensor = 'SENSOR'
    Actuator = 'ACTUATOR'


class MessageTypes(FieldEnumeration):
    Alert = 'ALERT'
    Control = 'CONTROL'
    Raw = 'RAW'
    Summary = 'SUMMARY'


class AlertMessageSubtypes(FieldEnumeration):
    Motion = 'MOTION'  # see comment at top of file
    Status = 'Status'
    Acknowledgement = 'Acknowledgement'


class ControlMessageSubtypes(FieldEnumeration):
    Activate = 'Activate'
    Config = 'Config'
    Cups = 'Cups'
    Deactivate = 'Deactivate'
    Dnsmasq = 'Dnsmasq'
    Heartbeat = 'Heartbeat'
    Light = 'Light'
    Microphone = 'Microphone'
    Ultrasonic = 'Ultrasonic'
    PoeCtl = 'PoeCtl'
    Reboot = 'Reboot'
    Refresh = 'Refresh'
    Speaker = 'Speaker'
    Status = 'Status'
    Voip = 'Voip'
    Workstation = 'Workstation'
    TV = 'Tv'
    SmartPowerStrip = 'Smartpowerstrip'


class RawMessageSubtypes(FieldEnumeration):
    Data = 'Data'
    LoadTest = 'LoadTest'
    UV = 'UV'
    HackRF = 'hackrf'
    ThermalCamera = 'thermalcam'
    ContactSensors = 'contactsensors'
    TemperatureHumidity = 'temphumid'
    DoorState = 'doorstate'
    GPIOPowerStrip = 'gpiopowerstrip'
    IPCamera = 'ipcamera'
    IRBeam = 'irbeam'
    PeopleDetection = 'peopledetection'
    GPIORelayController = 'gpiorelaycontroller'
    Lux = 'lux'
    AnalogUV = 'analoguv'
    SmartPowerStrip = 'smartpowerstrip'
    I2CRFID = 'i2crfid'
    ManualEvent = 'ManualEvent'
    Multicast = 'multicast'


class SummaryMessageSubtypes(FieldEnumeration):
    Todo = 'TODO'  # see comment at top of file


class SeverityTypes(FieldEnumeration):
    Emergency = 0
    Alert = 1
    Critical = 2
    Error = 3
    Warning = 4
    Notice = 5
    Informational = 6
    Debug = 7


class MessageBodyField(fields.Field):
    def _serialize(self, value, attr, obj, **kwargs):
        if isinstance(value, AlertBody) and obj.messageType == MessageTypes.Alert.value:
            return AlertBody.Schema().dump(value)
        elif isinstance(value, ControlBody) and obj.messageType == MessageTypes.Control.value:
            return ControlBody.Schema().dump(value)
        elif (isinstance(value, UVRawBody) and obj.messageType == MessageTypes.Raw.value
              and obj.messageSubtype == RawMessageSubtypes.UV.value):
            return UVRawBody.Schema().dump(value)
        elif isinstance(value, dict) and obj.messageType == MessageTypes.Raw.value:
            return value
        elif isinstance(value, SummaryBody) and obj.messageType == MessageTypes.Summary.value:
            return SummaryBody.Schema().dump(value)
        else:
            raise ValidationError('Unknown messageType {} and messageBody {} combination'.format(
                obj.messageType, type(value)
            ))

    def _deserialize(self, value, attr, data, **kawrgs):
        if data['messageType'] == MessageTypes.Alert.value:
            return AlertBody.Schema().load(value)
        elif data['messageType'] == MessageTypes.Control.value:
            return ControlBody.Schema().load(value)
        elif data['messageType'] == MessageTypes.Raw.value and data['messageSubtype'] == RawMessageSubtypes.UV.value:
            return UVRawBody.Schema().load(value)
        elif data['messageType'] == MessageTypes.Raw.value:
            return value
        elif data['messageType'] == MessageTypes.Summary.value:
            return SummaryBody.Schema().load(value)
        else:
            raise ValidationError('Unknown messageType')


@dataclass
class MessageBody:
    pass


@dataclass
class AlertBody(MessageBody):
    severity: int = field(metadata={
        'required': True,
        'validate': OneOf(SeverityTypes.values()),
    })

    confidence: int = field(metadata={
        'required': True,
        'validate': Range(1, 6)
    })

    host: str = field(metadata={
        'required': True,
        'allow_none': True
    })

    messageRef: List[str] = field(metadata={
        'required': True,
        # TODO 'validate': str,
    })

    alertTitle: str = field(metadata={
        'required': True,
        'validate': Length(max=50)
    })

    alertText: str = field(metadata={
        'required': True
    })

    alertDetail: dict = field(metadata={
        'required': True,
        'marshmallow_field': fields.Dict()
    })


@dataclass
class ControlBody(MessageBody):
    target: str = field(metadata={
        'required': True,
        'validate': str
    })

    commandTitle: str = field(metadata={
        'required': True,
        'validate': str
    })

    commandText: str = field(metadata={
        'required': True,
        'validate': str
    })

    commandDetail: dict = field(metadata={
        'required': True,
        'marshmallow_field': fields.Dict()
    })

    @validates_schema
    def validate_message_by_type(self, data, **kwargs):
        # populate this when we have commands that actually have detail
        pass


@dataclass
class RawBody(MessageBody):
    rawTitle: str = field(metadata={
        'required': True,
        'validate': Length(max=50)
    })
    rawDetail: dict = field(metadata={
        'required': True,
        'marshmallow_field': fields.Dict()
    })


@dataclass
class UVRawBody(MessageBody):
    visible: List[int] = field(metadata={
        'required': True,
    })
    uv: List[int] = field(metadata={
        'required': True,
    })
    ir: List[int] = field(metadata={
        'required': True,
    })
    timestamp: List[str] = field(metadata={
        'required': True,
    })


@dataclass
class SummaryBody(MessageBody):
    pass


@dataclass
class Message:
    """A Message is the core data type.  Everything is a message.
    """

    version: str = field(metadata={
        'required': True,
        'validate': Equal(f'{VERSION}'),
    })

    componentId: str = field(metadata={
        'required': True,
        'validate': Length(min=1),
    })

    componentType: str = field(metadata={
        'required': True,
        'validate': OneOf(ComponentTypes.values()),
    })

    componentSite: str = field(metadata={
        # The site of the component sending the message.  Valid characters
        # are alphanumeric and hyphen.  PascalCase is recommended.
        'required': True,
        'validate': Regexp('^[a-zA-Z0-9-]+$'),
    })

    componentFriendlyName: str = field(metadata={
        'required': True,
        'validate': str,  # I've never met a component name who wasn't a friend
    })

    messageTimestamp: str = field(metadata={
        'required': True,
        'validate': validate_datetimestamp,
        # apparently doesn't need separate validation method (see test)
    })

    messageId: str = field(metadata={
        'required': True,
        'validate': Length(min=1),
    })

    messageType: str = field(metadata={
        'required': True,
        'validate': OneOf(MessageTypes.values()),
    })

    messageSubtype: str = field(metadata={
        # The subtype of the message, as defined by the collector.  This is
        # included in the Kafka topic name and ElasticSearch index where the
        # message will be stored.  Valid characters are alphanumeric and
        # hyphen.  PascalCase is recommended.
        'required': True,
        'validate': Regexp('^[a-zA-Z0-9-]+$'),
        # TODO add a custom field for this composite enum
    })

    messageBody: MessageBody = field(metadata={
        'required': True,
        'marshmallow_field': MessageBodyField(),
        # validated in validate_message_by_type
    })

    @classmethod
    def validate_alert_message(cls, data):
        values = AlertMessageSubtypes.values()
        if not data['messageSubtype'] in values:
            raise ValidationError(f'Invalid alert message subtype: '
                                  f'{data["messageSubtype"]}.')
        AlertBody.Schema().validate(data['messageBody'])

    @classmethod
    def validate_control_message(cls, data):
        values = ControlMessageSubtypes.values()
        if not data['messageSubtype'] in values:
            raise ValidationError(f'Invalid control message subtype: '
                                  f'{data["messageSubtype"]}.')
        ControlBody.Schema().validate(data['messageBody'])

    @classmethod
    def validate_raw_message(cls, data):
        values = RawMessageSubtypes.values()
        if not data['messageSubtype'] in values:
            raise ValidationError(f'Invalid raw message subtype: '
                                  f'{data["messageSubtype"]}.')

    @classmethod
    def validate_summary_message(cls, data):
        values = SummaryMessageSubtypes.values()
        if not data['messageSubtype'] in values:
            raise ValidationError(f'Invalid summary message subtype: '
                                  f'{data["messageSubtype"]}.')
        SummaryBody.Schema().validate(data['messageBody'])

    @validates_schema
    def validate_message_by_type(self, data, **kwargs):
        try:
            if data['messageType'] == MessageTypes.Alert.value:
                Message.validate_alert_message(data)
            elif data['messageType'] == MessageTypes.Control.value:
                Message.validate_control_message(data)
            elif data['messageType'] == MessageTypes.Raw.value:
                Message.validate_raw_message(data)
            elif data['messageType'] == MessageTypes.Summary.value:
                Message.validate_summary_message(data)
        except KeyError:
            # Invalid message types are (apparently) handled before we get
            # here, so I don't think we need to worry if the messageType
            # is omitted.
            pass
