# coding=utf-8
# Copyright (c) 2015 EMC Corporation.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
from __future__ import unicode_literals

import logging

import re
import six

from storops.lib.ex_decorator_factory import MappedErrorCodeDecoratorFactory, \
    ExceptionListDecoratorFactory

__author__ = 'Cedric Zhuang'

log = logging.getLogger(__name__)


class StoropsException(Exception):
    """Base Storops Exception

    To correctly use this class, inherit from it and define
    a 'message' property. That message will be formatted
    with the keyword arguments provided to the constructor.

    """
    message = "An unknown exception occurred."
    code = 500
    headers = {}

    def __init__(self, message=None, **kwargs):
        if message is None:
            message = self.message

        self.kwargs = self._insert_default_code(kwargs)
        self.message = self._update_message(message, kwargs)

        super(StoropsException, self).__init__(self.message)

    @staticmethod
    def _update_message(message, kwargs):
        if isinstance(message, six.string_types):
            try:
                message = message.format(**kwargs)

            except KeyError:
                # kwargs doesn't match a variable in the message
                # log the issue and the kwargs
                log.error(
                    'missing param in format string: "{}"'.format(message))
            except IndexError:
                # format error, use original message
                pass
        elif isinstance(message, Exception):
            message = six.text_type(message)

        return message

    @classmethod
    def _insert_default_code(cls, kwargs):
        if 'code' not in kwargs:
            try:
                kwargs['code'] = cls.code
            except AttributeError:
                pass
        for k, v in six.iteritems(kwargs):
            if isinstance(v, Exception):
                kwargs[k] = six.text_type(v)
        return kwargs


def to_hex(number):
    if number is not None:
        h = hex(number)
        if h.endswith('L'):
            h = h[:-1]
    else:
        h = None
    return h


class VNXException(StoropsException):
    @classmethod
    def get_error_message(cls):
        ret = None
        if hasattr(cls, 'error_code'):
            ret = to_hex(cls.error_code)
        elif hasattr(cls, 'error_message'):
            ret = cls.error_message
        elif hasattr(cls, 'error_regex'):
            flags = re.IGNORECASE | re.MULTILINE | re.DOTALL
            ret = re.compile(cls.error_regex, flags=flags)

        if ret is None:
            raise AttributeError('"error_code" or "error_message" must be '
                                 'specified for VNX CLI error.')
        return ret


class UnityException(StoropsException):
    def __init__(self, error=None):
        super(UnityException, self).__init__()
        self.error = error

    def __str__(self):
        if hasattr(self.error, 'get_messages'):
            ret = '.  '.join(self.error.get_messages())
        elif isinstance(self.error, six.string_types):
            ret = self.error
        elif hasattr(self, 'message'):
            ret = self.message
        else:
            ret = self.error
        return ret

    @property
    def error_code(self):
        if self.error is not None:
            ret = self.error.error_code
        else:
            ret = None
        return ret


class VNXBackendError(VNXException):
    message = "vnx backend error.  {err}"


_rest_exception_factory = MappedErrorCodeDecoratorFactory(
    default_exception=UnityException)
get_rest_exception = _rest_exception_factory.get_exception
rest_exception = _rest_exception_factory.clz_decorator()
rest_exception.__doc__ = """ class decorator for Unity REST exceptions

Each Unity REST exception has a designated error code.
When a Unity error is received from REST, we search in all registered
Unity exception and throw the matched one.

:param clz: the exception class
:return: the input exception class
"""

_xmlapi_exception_factory = MappedErrorCodeDecoratorFactory(
    default_exception=VNXBackendError)
get_xmlapi_exception = _xmlapi_exception_factory.get_exception
xmlapi_exception = _xmlapi_exception_factory.clz_decorator()
xmlapi_exception.__doc__ = """ class decorator for VNX File XML API exceptions

Each error from XML API has a unique error code.  We will search all
registered XML API exception and throw the matched one.

:param clz: the exception class
:return: the input exception class
"""

_cli_exception_factory = ExceptionListDecoratorFactory(
    default_exception=VNXException)
get_cli_exception = _cli_exception_factory.get_exception
cli_exception = _cli_exception_factory.clz_decorator()
cli_exception.__doc__ = """ class decorator for VNX CLI exceptions

The decorated exception classes will be used as exception candidate.
When an error message is received in CLI, we will search all CLI
exceptions and throw the matched on.

Each class must either have `error_code` or `error_message` property.

:param clz: the exception class
:return: the input exception class
"""


def _extract_output(output):
    if output is not None and not isinstance(output, six.string_types):
        if hasattr(output, 'message'):
            output = output.message
        elif hasattr(output, 'why'):
            # for EvError
            output = getattr(output, 'why')
        elif hasattr(output, 'hex_problem_message_codes'):
            codes = getattr(output, 'hex_problem_message_codes')
            output = ' '.join(codes)
    return output


def raise_if_err(out, msg=None, default=None):
    out = _extract_output(out)
    ex_clz = get_cli_exception(out, default)

    if msg is None:
        if hasattr(out, 'get_status_msg'):
            msg = out.get_status_msg()
        else:
            msg = out
    else:
        msg = '{}  detail:\n{}'.format(msg, out)

    # check if out is empty
    if out is not None and len(out) > 0:
        raise ex_clz(msg)


def check_error(out, *ex_clz_list):
    """ check whether this cli output contains the specified exception

    :param out: output of naviseccli
    :param ex_clz_list: exception class to check
    :return: nothing, raise `ex_clz` if match
    """
    try:
        raise_if_err(out)
    except ex_clz_list:
        raise
    except StoropsException:
        # swallow other errors
        pass
    return out


def check_nas_cmd_error(output, default=None):
    if default is None:
        default = VNXNasCommandNoError

    try:
        raise_if_err(output, default=default)
    except VNXNasCommandNoError:
        # meaning no error
        pass
    except:
        # re-raise the error
        raise


class EnumValueNotFoundError(StoropsException, ValueError):
    pass


class MockFileNotFoundError(StoropsException):
    pass


class NoIndexException(StoropsException):
    pass


class UnityNameNotUniqueError(UnityException):
    def __init__(self, message="multiple objects found", objects=None):
        super(UnityNameNotUniqueError, self).__init__()
        self.message = message
        self.objects = objects


class UnityCifsServiceNotEnabledError(UnityException):
    pass


class UnityHostInitiatorNotFoundError(UnityException):
    pass


class UnityHostInitiatorUnknownType(UnityException):
    pass


class UnityAttachAluError(UnityException):
    pass


class UnityHostNameInUseError(UnityException):
    pass


@rest_exception
class UnityLunNameInUseError(UnityException):
    error_code = 108007744


@rest_exception
class UnityAttachAluExceedLimitError(UnityAttachAluError):
    error_code = 108008750
    message = "Numbers of LUNs exceeds system limit"


class UnityAluAlreadyAttachedError(UnityAttachAluError):
    message = 'Requested LUN has already been added to this host'


@rest_exception
class UnityResourceNotFoundError(UnityException):
    error_code = 131149829


@rest_exception
class UnityNasServerNameUsedError(UnityException):
    error_code = 108011556


@rest_exception
class UnityNasServerHasFsError(UnityException):
    error_code = 108011564


@rest_exception
class UnitySmbNameInUseError(UnityException):
    error_code = 108011873


@rest_exception
class UnityIpAddressUsedError(UnityException):
    error_code = 108011747


@rest_exception
class UnityOneDnsPerNasServerError(UnityException):
    error_code = 108012064


@rest_exception
class UnitySmbShareNameExistedError(UnityException):
    error_code = 151036420


@rest_exception
class UnityNfsShareNameExistedError(UnityException):
    error_code = 151036164


@rest_exception
class UnityOneSmbServerPerNasServerError(UnityException):
    error_code = 108011888


@rest_exception
class UnityNetBiosNameExistedError(UnityException):
    error_code = 108011876


@rest_exception
class UnityNfsAlreadyEnabledError(UnityException):
    error_code = 108012128


@rest_exception
class UnityFileSystemNameAlreadyExisted(UnityException):
    error_code = 108008464


class UnityCreateSnapError(UnityException):
    pass


@rest_exception
class UnitySnapNameInUseError(UnityException):
    error_code = (1903001605, 1903132675)


@rest_exception
class UnityShareOnCkptSnapError(UnityException):
    error_code = 1903001786


@rest_exception
class UnityHostIpInUseError(UnityException):
    error_code = 100663538


@rest_exception
class UnitySmbServerLockedError(UnityException):
    error_code = 108011909


@rest_exception
class UnityAclUserNotFoundError(UnityException):
    error_code = 100663499


@rest_exception
class UnityFileSystemSizeTooSmallError(UnityException):
    error_code = 108008449


class UnityShareTypeNotSupportAccessControlError(UnityException):
    message = 'share type does not support access control.'


class UnityHostNotFoundException(UnityException):
    message = 'specified host not found.'


class NaviseccliNotAvailableError(VNXException):
    message = ("naviseccli not found.  please make sure it's installed"
               " and available in path.")


class VNXObjectNotFound(VNXException):
    message = "object is not found.  {err}"


class OptionMissingError(VNXException):
    pass


@xmlapi_exception
class VNXInvalidMoverID(VNXException):
    error_code = 14227341323
    message = "invalid mover or vdm.  {id}"


class VNXLockRequiredException(VNXException):
    message = "unable to acquire lock."


@cli_exception
class VNXSpNotAvailableError(VNXException):
    error_message = ('connection refused',
                     'A network error occurred while trying to connect')


@cli_exception
class VNXDropConnectionError(VNXException):
    error_message = 'End of data stream'


@cli_exception
class VNXNotSupportedError(VNXException):
    error_message = 'commands are not supported by the target storage system'


class VNXSystemError(VNXException):
    pass


class VNXSystemDownError(VNXSystemError):
    pass


class VNXSPError(VNXException):
    pass


class VNXSPDownError(VNXSPError):
    pass


class VNXStorageGroupError(VNXException):
    pass


class VNXAttachAluError(VNXException):
    pass


@cli_exception
class VNXInvalidCliParamError(VNXException):
    error_message = 'invalid command line parameters'


@cli_exception
class VNXPortNotInitializedError(VNXStorageGroupError):
    error_message = 'port is uninitialized'


@cli_exception
class VNXInitiatorExistedError(VNXStorageGroupError):
    error_message = 'Initiator record already exists'


@cli_exception
class VNXAluAlreadyAttachedError(VNXAttachAluError):
    error_message = (
        'LUN already exists in the specified storage group',
        'Requested LUN has already been added to this Storage Group')


@cli_exception
class VNXAluNotFoundError(VNXAttachAluError):
    error_message = 'The ALU number specified by user is not a bound'


@cli_exception
class VNXHluNumberInUseError(VNXAttachAluError):
    error_message = 'Requested Host LUN Number already in use'


class VNXDetachAluError(VNXStorageGroupError):
    pass


@cli_exception
class VNXDetachAluNotFoundError(VNXDetachAluError):
    error_message = 'No such Host LUN in this Storage Group'


class VNXCreateStorageGroupError(VNXStorageGroupError):
    pass


@cli_exception
class VNXStorageGroupNameInUseError(VNXCreateStorageGroupError):
    error_message = 'Storage Group name already in use'


class VNXDeleteStorageGroupError(VNXStorageGroupError):
    pass


@cli_exception
class VNXStorageGroupNotFoundError(VNXStorageGroupError):
    error_message = ('The group name or UID does not match any '
                     'storage groups for this array')


class VNXNoHluAvailableError(VNXStorageGroupError):
    pass


class VNXMigrationError(VNXException):
    pass


@cli_exception
class VNXLunNotMigratingError(VNXMigrationError):
    error_message = 'The specified source LUN is not currently migrating.'


@cli_exception
class VNXTargetNotReadyError(VNXMigrationError):
    error_message = 'The destination LUN is not available for migration'


class VNXSnapError(VNXException):
    pass


class VNXModifySnapError(VNXSnapError):
    pass


@cli_exception
class VNXDeleteAttachedSnapError(VNXSnapError):
    error_code = 0x716d8003


@cli_exception
class VNXSnapAlreadyMountedError(VNXSnapError):
    error_code = 0x716d8055


@cli_exception
class VNXSnapNotAttachedError(VNXSnapError):
    error_message = 'Snapshot mount point is not currently attached.'


class VNXCreateSnapError(VNXException):
    pass


class VNXAttachSnapError(VNXSnapError):
    pass


@cli_exception
class VNXAttachSnapLunTypeError(VNXAttachSnapError):
    error_message = 'Cannot attach the snapshot. Invalid LUN type.'


class VNXDetachSnapError(VNXSnapError):
    pass


@cli_exception
class VNXDetachSnapLunTypeError(VNXDetachSnapError):
    error_message = 'it is not a snapshot mount point.'


@cli_exception
class VNXSnapNameInUseError(VNXSnapError):
    error_code = 0x716d8005


@cli_exception
class VNXCreateSnapResourceNotFoundError(VNXSnapError):
    error_message = 'The specified resource does not exist.'


class VNXDeleteSnapError(VNXSnapError):
    pass


@cli_exception
class VNXSnapNotExistsError(VNXSnapError):
    error_message = 'The specified snapshot does not exist.'


class VNXLunError(VNXException):
    pass


class VNXCreateLunError(VNXLunError):
    pass


@cli_exception
class VNXLunNameInUseError(VNXCreateLunError):
    error_code = 0x712d8d04


class VNXModifyLunError(VNXLunError):
    pass


class VNXCreateMpError(VNXLunError):
    pass


class VNXLunExtendError(VNXLunError):
    pass


@cli_exception
class VNXNotReadyExpandError(VNXLunExtendError):
    error_code = 0x712d8d33


@cli_exception
class VNXLunExpandSizeError(VNXLunExtendError):
    error_code = 0x712d8e04


@cli_exception
class VNXLunPreparingError(VNXLunError):
    error_code = 0x712d8e0e


@cli_exception
class VNXLunNotFoundError(VNXLunError):
    error_message = 'Could not retrieve the specified (pool lun).'


class VNXDeleteLunError(VNXLunError):
    pass


@cli_exception
class VNXLunInStorageGroupError(VNXDeleteLunError):
    error_message = ('contained in a Storage Group',
                     'LUN mapping still exists')


@cli_exception
class VNXLunInConsistencyGroupError(VNXDeleteLunError):
    error_code = 0x716d8025


@cli_exception
class VNXLunHasSnapMountPointError(VNXDeleteLunError):
    error_code = 0x716d801a


class VNXCompressionError(VNXLunError):
    pass


@cli_exception
class VNXCompressionAlreadyEnabledError(VNXCompressionError):
    error_message = 'Compression on the specified LUN is already turned on.'


class VNXDedupError(VNXLunError):
    pass


@cli_exception
class VNXDedupAlreadyEnabled(VNXDedupError):
    error_message = ['Deduplication is already enabled',
                     'the deduplication state of LUN is enabled or enabling.']


class VNXConsistencyGroupError(VNXException):
    pass


class VNXCreateConsistencyGroupError(VNXConsistencyGroupError):
    pass


@cli_exception
class VNXConsistencyGroupNameInUseError(VNXCreateConsistencyGroupError):
    error_code = 0x716d8021


@cli_exception
class VNXConsistencyGroupNotFoundError(VNXConsistencyGroupError):
    error_message = 'Cannot find the consistency group'


@cli_exception
class VNXConsistencyGroupIsDeletingError(VNXConsistencyGroupError):
    error_code = 0x712d8801


class VNXDeleteHbaError(VNXException):
    pass


@cli_exception
class VNXDeleteHbaNotFoundError(VNXException):
    error_message = 'The HBA UID specified is not known by the array'


class VNXPingNodeError(VNXException):
    pass


@cli_exception
class VNXPingNodeTimeOutError(VNXPingNodeError):
    error_message = 'Request timed out.'


@cli_exception
class VNXPingNodeSuccess(VNXPingNodeError):
    error_regex = 'TTL=\w+'


class VNXSecurityException(VNXException):
    pass


@cli_exception
class VNXCredentialError(VNXSecurityException):
    error_message = ['invalid username, password and/or scope.',
                     'Could not connect to the specified host']


@cli_exception
class VNXUserNameInUseError(VNXSecurityException):
    error_message = 'The specified user already exists.'


@cli_exception
class VNXUserNotFoundError(VNXSecurityException):
    error_message = 'User does not exist'


class VNXRaidGroupError(VNXException):
    pass


class VNXCreateRaidGroupError(VNXRaidGroupError):
    pass


class VNXDeleteRaidGroupError(VNXRaidGroupError):
    pass


class VNXPoolError(VNXException):
    pass


class VNXCreatePoolError(VNXPoolError):
    pass


@cli_exception
class VNXPoolNameInUseError(VNXCreatePoolError):
    error_message = ['0x712d8501', 'Pool name is already used']


@cli_exception
class VNXDiskUsedError(VNXCreatePoolError):
    error_code = 0x76008304


class VNXModifyPoolError(VNXPoolError):
    pass


class VNXDeletePoolError(VNXPoolError):
    pass


@cli_exception
class VNXPoolDestroyingError(VNXDeletePoolError):
    error_message = 'the Storage Pool because it is Destroying'


@cli_exception
class VNXPoolNotFoundError(VNXPoolError):
    error_message = ['The (Storagepool) may not exist',
                     'was not found in any provider']


class VNXNotEnoughDiskAvailableError(VNXPoolError):
    message = 'not enough disk for pool creation.'


class VNXMirrorException(VNXException):
    pass


@cli_exception
class VNXMirrorLunNotAvailableError(VNXMirrorException):
    error_message = 'Specified LU not available for mirroring.'


@cli_exception
class VNXMirrorNameInUseError(VNXMirrorException):
    error_message = 'Mirror name already in use'


@cli_exception
class VNXMirrorAlreadyMirroredError(VNXMirrorException):
    error_message = ('A mirror image for the specified mirror '
                     'already exists on the chosen subsystem')


@cli_exception
class VNXMirrorImageNotFoundError(VNXMirrorException):
    error_message = 'Image not found'


@cli_exception
class VNXMirrorFractureImageError(VNXMirrorException):
    error_message = 'Cannot fracture the image because of'


@cli_exception
class VNXMirrorSyncImageError(VNXMirrorException):
    error_message = 'Synchronizing sync mirror image failed'


@cli_exception
class VNXMirrorPromoteNonLocalImageError(VNXMirrorException):
    error_code = 0x7105824e


@cli_exception
class VNXMirrorRemoveSynchronizingError(VNXMirrorException):
    error_code = 0x71058247


@cli_exception
class VNXMirrorPromotePrimaryError(VNXMirrorException):
    error_message = 'Cannot remove or promote a primary image.'


@cli_exception
class VNXMirrorFeatureNotAvailableError(VNXMirrorException):
    error_message = 'Mirror Feature software is not installed'


@cli_exception
class VNXMirrorNotFoundError(VNXMirrorException):
    error_message = 'Mirror not found'


@cli_exception
class VNXDeleteMirrorWithSecondaryError(VNXMirrorException):
    error_code = 0x71058243


class VNXPortError(VNXException):
    pass


@cli_exception
class VNXGateWayError(VNXException):
    error_message = ('The gateway is not on the subnet defined '
                     'by the IP address and netmask.')


@cli_exception
class VNXVirtualPortNotFoundError(VNXPortError):
    error_message = 'Request failed. Specified virtual port not found.'


@xmlapi_exception
class VNXGeneralNasError(VNXException):
    error_code = 13690601492


class VNXVdmError(VNXException):
    pass


@xmlapi_exception
class VNXInvalidVdmIdError(VNXVdmError):
    error_code = 13421840550


@xmlapi_exception
class VNXVdmAlreadyExistedError(VNXVdmError):
    error_code = 13421840550


class VNXFsError(VNXException):
    pass


@xmlapi_exception
class VNXFsExistedError(VNXFsError):
    error_code = 13691191325


@xmlapi_exception
class VNXFsNotFoundError(VNXFsError):
    error_code = 18522112101


class VNXFsSnapError(VNXException):
    pass


@xmlapi_exception
class VNXFsSnapNameInUseError(VNXFsSnapError):
    error_code = 13690535947


class VNXMoverInterfaceError(VNXException):
    pass


@xmlapi_exception
class VNXMoverInterfaceNotFoundError(VNXMoverInterfaceError):
    error_code = 13691781134


@cli_exception
class VNXMoverInterfaceNotAttachedError(VNXMoverInterfaceError):
    error_message = 'is not currently attached to the VDM'


@xmlapi_exception
class VNXMoverInterfaceInvalidVlanIdError(VNXMoverInterfaceError):
    error_code = 13421850371


@xmlapi_exception
class VNXMoverInterfaceExistedError(VNXMoverInterfaceError):
    error_code = 13691781136


@xmlapi_exception
class VNXMoverInterfaceNameInUseError(VNXMoverInterfaceError):
    error_code = 13421840550


class VNXFileCredentialError(VNXCredentialError):
    message = 'credential error for VNX control station.'


class VNXNasCommandNoError(VNXException):
    """ Nas command returns something even if command success.

    Use this error as the default exception for output verification.
    If this exception is thrown, we know that no error is found.
    """
    pass


@cli_exception
class VNXMoverInterfaceNotExistsError(VNXMoverInterfaceError):
    error_regex = 'network interface .* does not exist'
