from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from app.schema.base_model import BaseModel

def safe_int(value, default=None):
    """Safely convert a value to int, handling None and string integers"""
    if value is None:
        return default
    
    # Convert float values to int if they represent whole numbers
    if isinstance(value, float):
        if value == int(value):  # Check if it's a whole number
            return int(value)
        else:
            return default  # Return default for non-whole floats
        
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

@dataclass
class SystemConfigDriveTypes:
    """Configuration data for SANtricity system drive types ['sas']"""
    driveMediaType: Optional[List[str]] = None
    # Add fields from schema.md that have high occurrence rates
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'SystemConfigDriveTypes':
        return SystemConfigDriveTypes(
            driveMediaType=data.get('driveMediaType'),            
            _raw_data=data.copy()
        )
    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class SystemConfig(BaseModel):
    """Configuration data for SANtricity system configuration"""
    asupEnabled: Optional[bool] = None
    autoLoadBalancingEnabled: Optional[bool] = None
    chassisSerialNumber: Optional[str] = None
    driveCount: Optional[int] = None
    driveTypes: Optional[List[SystemConfigDriveTypes]] = None
    freePoolSpace: Optional[int] = None
    hostSpareCountInStandby: Optional[int] = None
    hostSparesUsed: Optional[int] = None
    hotSpareCount: Optional[int] = None
    mediaScanPeriod: Optional[int] = None
    model: Optional[str] = None
    name: Optional[str] = None
    status: Optional[str] = None
    unconfiguredSpace: Optional[int] = None
    # unconfiguredSpaceByDriveType: Optional[Dict[str, int]] = None # interesting
    usedPoolSpace: Optional[int] = None
    wwn: Optional[str] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'SystemConfig':
        drive_types = None
        if data.get("driveTypes"):
            # Handle both string arrays and object arrays
            drive_types_data = data.get("driveTypes") or []
            if drive_types_data and isinstance(drive_types_data[0], str):
                # If it's a list of strings, create objects with driveMediaType
                drive_types = [SystemConfigDriveTypes(driveMediaType=[dt]) for dt in drive_types_data]
            else:
                # If it's a list of objects, parse normally
                drive_types = [SystemConfigDriveTypes.from_api_response(m) for m in drive_types_data]
        return SystemConfig(
            asupEnabled=data.get('asupEnabled'),
            autoLoadBalancingEnabled=data.get('autoLoadBalancingEnabled'),
            chassisSerialNumber=data.get('chassisSerialNumber'),
            driveCount=data.get('driveCount'),
            driveTypes=drive_types,
            freePoolSpace=data.get('freePoolSpace'),
            hostSpareCountInStandby=data.get('hostSpareCountInStandby'),
            hostSparesUsed=data.get('hostSparesUsed'),
            hotSpareCount=data.get('hotSpareCount'),
            mediaScanPeriod=data.get('mediaScanPeriod'),
            model=data.get('model'),
            name=data.get('name', 'unknown'),
            status=data.get('status'),
            unconfiguredSpace=data.get('unconfiguredSpace'),
            usedPoolSpace=data.get('usedPoolSpace'),
            wwn=data.get('wwn', 'unknown'),
            _raw_data=data.copy()
        )
    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class ControllerConfigNetInterfaceEthernet:
    """Ethernet interface configuration for controller network interfaces"""
    interfaceName: Optional[str] = None
    interfaceRef: Optional[str] = None
    controllerRef: Optional[str] = None
    linkStatus: Optional[str] = None
    currentSpeed: Optional[str] = None
    channel: Optional[int] = None
    macAddr: Optional[str] = None
    ipv4Address: Optional[str] = None
    ipv4Enabled: Optional[bool] = None
    fullDuplex: Optional[bool] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)
    
    @staticmethod
    def from_dict(data: Dict) -> 'ControllerConfigNetInterfaceEthernet':
        if not data:
            return ControllerConfigNetInterfaceEthernet(_raw_data={})
        return ControllerConfigNetInterfaceEthernet(
            interfaceName=data.get('interfaceName'),
            interfaceRef=data.get('interfaceRef'),
            controllerRef=data.get('controllerRef'),
            linkStatus=data.get('linkStatus'),
            currentSpeed=data.get('currentSpeed'),
            channel=safe_int(data.get('channel')),
            macAddr=data.get('macAddr'),
            ipv4Address=data.get('ipv4Address'),
            ipv4Enabled=data.get('ipv4Enabled'),
            fullDuplex=data.get('fullDuplex'),
            _raw_data=data.copy()
        )
    
    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class ControllerConfigHostInterfaceIB:
    """InfiniBand interface configuration for controller host interfaces"""
    interfaceRef: Optional[str] = None
    controllerRef: Optional[str] = None
    linkState: Optional[str] = None  # IB uses linkState instead of linkStatus
    currentSpeed: Optional[str] = None
    channel: Optional[int] = None
    localIdentifier: Optional[int] = None
    globalIdentifier: Optional[str] = None
    portState: Optional[str] = None
    maximumTransmissionUnit: Optional[int] = None
    currentLinkWidth: Optional[str] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)
    
    @staticmethod
    def from_dict(data: Dict) -> 'ControllerConfigHostInterfaceIB':
        if not data:
            return ControllerConfigHostInterfaceIB(_raw_data={})
        return ControllerConfigHostInterfaceIB(
            interfaceRef=data.get('interfaceRef'),
            controllerRef=data.get('controllerRef'),
            linkState=data.get('linkState'),
            currentSpeed=data.get('currentSpeed'),
            channel=safe_int(data.get('channel')),
            localIdentifier=safe_int(data.get('localIdentifier')),
            globalIdentifier=data.get('globalIdentifier'),
            portState=data.get('portState'),
            maximumTransmissionUnit=safe_int(data.get('maximumTransmissionUnit')),
            currentLinkWidth=data.get('currentLinkWidth'),
            _raw_data=data.copy()
        )
    
    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class ControllerConfigHostInterfaceISCSI:
    """iSCSI interface configuration for controller host interfaces"""
    interfaceRef: Optional[str] = None
    controllerRef: Optional[str] = None
    linkStatus: Optional[str] = None
    currentSpeed: Optional[str] = None
    channel: Optional[int] = None
    ipv4Address: Optional[str] = None
    ipv4Enabled: Optional[bool] = None
    tcpListenPort: Optional[int] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)
    
    @staticmethod
    def from_dict(data: Dict) -> 'ControllerConfigHostInterfaceISCSI':
        if not data:
            return ControllerConfigHostInterfaceISCSI(_raw_data={})
        return ControllerConfigHostInterfaceISCSI(
            interfaceRef=data.get('interfaceRef'),
            controllerRef=data.get('controllerRef'),
            linkStatus=data.get('linkStatus'),
            currentSpeed=data.get('currentSpeed'),
            channel=safe_int(data.get('channel')),
            ipv4Address=data.get('ipv4Address'),
            ipv4Enabled=data.get('ipv4Enabled'),
            tcpListenPort=safe_int(data.get('tcpListenPort')),
            _raw_data=data.copy()
        )
    
    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class ControllerConfigNetInterface:
    """Network interface configuration (for netInterfaces array)"""
    interfaceType: Optional[str] = None
    ethernet: Optional[ControllerConfigNetInterfaceEthernet] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)
    
    @staticmethod
    def from_dict(data: Dict) -> 'ControllerConfigNetInterface':
        if not data:
            return ControllerConfigNetInterface(_raw_data={})
        
        ethernet_data = None
        if data.get('ethernet'):
            ethernet_data = ControllerConfigNetInterfaceEthernet.from_dict(data['ethernet'])
        
        return ControllerConfigNetInterface(
            interfaceType=data.get('interfaceType'),
            ethernet=ethernet_data,
            _raw_data=data.copy()
        )
    
    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class ControllerConfigHostInterface:
    """Host interface configuration (for hostInterfaces array)"""
    interfaceType: Optional[str] = None
    ib: Optional[ControllerConfigHostInterfaceIB] = None
    iscsi: Optional[ControllerConfigHostInterfaceISCSI] = None
    # Note: Other interface types (sas, fibre, etc.) can be added later as needed
    _raw_data: Dict[str, Any] = field(default_factory=dict)
    
    @staticmethod
    def from_dict(data: Dict) -> 'ControllerConfigHostInterface':
        if not data:
            return ControllerConfigHostInterface(_raw_data={})
        
        ib_data = None
        iscsi_data = None
        
        if data.get('ib'):
            ib_data = ControllerConfigHostInterfaceIB.from_dict(data['ib'])
        if data.get('iscsi'):
            iscsi_data = ControllerConfigHostInterfaceISCSI.from_dict(data['iscsi'])
        
        return ControllerConfigHostInterface(
            interfaceType=data.get('interfaceType'),
            ib=ib_data,
            iscsi=iscsi_data,
            _raw_data=data.copy()
        )
    
    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class ControllerConfig(BaseModel):
    """Configuration data for controllerconfig"""
    active: Optional[bool] = None
    cacheMemorySize: Optional[int] = None
    # [{'codeModule': 'raid', 'versionString': '08.90.04.00'}]
    # codeVersions: Optional[List[Dict[str, str]]] = None
    controllerErrorModel: Optional[str] = None
    controllerRef: Optional[str] = None
    # driveInterfaces: Optional[List[Dict[str, Any]]] = None
    flashCacheMemorySize: Optional[int] = None
    hostInterfaces: Optional[List[ControllerConfigHostInterface]] = None
    id: Optional[str] = None
    manufacturer: Optional[str] = None
    modelName: Optional[str] = None
    netInterfaces: Optional[List[ControllerConfigNetInterface]] = None
    # networkSettings: Optional[List[Dict]] = None
    partNumber: Optional[str] = None
    # physicalLocation: Optional[Dict[str, Any]] = None
    serialNumber: Optional[str] = None
    status: Optional[str] = None    
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'ControllerConfig':
        # Parse host interfaces
        host_interfaces = None
        if data.get('hostInterfaces'):
            host_interfaces = [
                ControllerConfigHostInterface.from_dict(interface)
                for interface in data['hostInterfaces']
            ]
        
        # Parse net interfaces
        net_interfaces = None
        if data.get('netInterfaces'):
            net_interfaces = [
                ControllerConfigNetInterface.from_dict(interface)
                for interface in data['netInterfaces']
            ]
        
        return ControllerConfig(
            active=data.get('active'),
            cacheMemorySize=data.get('cacheMemorySize'),
            # codeVersions=data.get('codeVersions'),
            controllerErrorModel=data.get('controllerErrorModel'),
            controllerRef=data.get('controllerRef'),
            # driveInterfaces=data.get('driveInterfaces'),
            flashCacheMemorySize=data.get('flashCacheMemorySize'),
            hostInterfaces=host_interfaces,
            id=data.get('id', 'unknown'),
            manufacturer=data.get('manufacturer'),
            modelName=data.get('modelName'),
            netInterfaces=net_interfaces,
            # networkSettings=data.get('networkSettings'),
            partNumber=data.get('partNumber'),
            # physicalLocation=data.get('physicalLocation'),
            serialNumber=data.get('serialNumber'),
            status=data.get('status'),
            _raw_data=data.copy()
        )
    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class DriveConfigPhysicalLocation:
    '''Physical location data for drives.
    Example: {'trayRef': '0E00000000000000000000000000000000000000', 'slot': 24, 'locationParent': {'refType': 'genericTyped', 'controllerRef': None, 'symbolRef': None, 'typedReference':       │
    {'componentType': 'tray', 'symbolRef': '0E00000000000000000000000000000000000000'}}, 'locationPosition': 24, 'label': '23'} 
    '''
    label: Optional[str] = None
    # locationParent: Optional[Dict[str, Any]] = None # Nested object, keep as dict
    locationPosition: Optional[int] = None
    slot: Optional[int] = None
    trayRef: Optional[str] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

    @staticmethod
    def from_dict(data: Dict) -> 'DriveConfigPhysicalLocation':
        return DriveConfigPhysicalLocation(
            label=data.get('label'),
            # locationParent=data.get('locationParent'),
            locationPosition=data.get('locationPosition'),
            slot=data.get('slot'),
            trayRef=data.get('trayRef'),
            _raw_data=data.copy()
        )

@dataclass
class DriveConfigSsdWearLife:
    """
    {'averageEraseCountPercent': 8, 'spareBlocksRemainingPercent': 100, 
    'isWearLifeMonitoringSupported': True, 'percentEnduranceUsed': 8}
   """ 
    averageEraseCountPercent: Optional[int] = None
    isWearLifeMonitoringSupported: Optional[bool] = None
    percentEnduranceUsed: Optional[int] = None
    spareBlocksRemainingPercent: Optional[int] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)    
    
    @staticmethod
    def from_dict(data: Dict) -> 'DriveConfigSsdWearLife':
         return DriveConfigSsdWearLife(
              averageEraseCountPercent=data.get('averageEraseCountPercent'),
              isWearLifeMonitoringSupported=data.get('isWearLifeMonitoringSupported'),
              percentEnduranceUsed=data.get('percentEnduranceUsed'),
              spareBlocksRemainingPercent=data.get('spareBlocksRemainingPercent'),
              _raw_data=data.copy()
         )
    def get_raw(self, key, default=None):
         """Access any field from the raw data"""
         return self._raw_data.get(key, default)

@dataclass
class DriveConfig(BaseModel):
    """Configuration data for drives"""
    available: Optional[bool] = None
    blkSize: Optional[int] = None
    blkSizePhysical: Optional[int] = None
    cause: Optional[str] = None
    currentSpeed: Optional[str] = None
    currentVolumeGroupRef: Optional[str] = None
    degradedChannels: Optional[List[Any]] = None
    driveMediaType: Optional[str] = None
    driveRef: Optional[str] = None
    driveSecurityType: Optional[str] = None
    dulbeCapable: Optional[bool] = None
    fdeCapable: Optional[bool] = None
    fdeEnabled: Optional[bool] = None
    fdeLocked: Optional[bool] = None
    fipsCapable: Optional[bool] = None
    firmwareVersion: Optional[str] = None
    hasDegradedChannel: Optional[bool] = None
    hotSpare: Optional[bool] = None
    id: Optional[str] = None
    # interfaceType: Optional[Dict] = None
    # interposerPresent: Optional[bool] = None
    # interposerRef: Optional[str] = None
    invalidDriveData: Optional[bool] = None
    lowestAlignedLBA: Optional[str] = None
    manufacturer: Optional[str] = None
    manufacturerDate: Optional[str] = None
    maxSpeed: Optional[str] = None
    mirrorDrive: Optional[str] = None
    nonRedundantAccess: Optional[bool] = None
    offline: Optional[bool] = None
    # pfa: Optional[bool] = None
    # pfaReason: Optional[str] = None
    phyDriveType: Optional[str] = None
    # phyDriveTypeData: Optional[Dict] = None
    physicalLocation: Optional[DriveConfigPhysicalLocation] = None
    productID: Optional[str] = None
    rawCapacity: Optional[int] = None
    sanitizeCapable: Optional[bool] = None
    serialNumber: Optional[str] = None
    softwareVersion: Optional[str] = None
    sparedForDriveRef: Optional[str] = None
    spindleSpeed: Optional[int] = None
    ssdWearLife: Optional[DriveConfigSsdWearLife] = None    
    status: Optional[str] = None
    uncertified: Optional[bool] = None
    usableCapacity: Optional[str] = None
    volumeGroupIndex: Optional[int] = None
    workingChannel: Optional[int] = None
    worldWideName: Optional[str] = None
    # Add fields from schema.md that have high occurrence rates
    _raw_data: Dict[str, Any] = field(default_factory=dict)
    
    # Static method to create from API response
    @staticmethod
    def from_api_response(data: Dict) -> 'DriveConfig':
        """Create a DriveConfig instance from API response data"""
        return DriveConfig(
            available=data.get("available"),
            blkSize=safe_int(data.get("blkSize")),
            blkSizePhysical=safe_int(data.get("blkSizePhysical")),
            cause=data.get("cause"),
            currentSpeed=data.get("currentSpeed"),
            currentVolumeGroupRef=data.get("currentVolumeGroupRef"),
            degradedChannels=data.get("degradedChannels"),
            driveMediaType=data.get("driveMediaType"),
            driveRef=data.get("driveRef"),
            driveSecurityType=data.get("driveSecurityType"),
            dulbeCapable=data.get("dulbeCapable"),
            fdeCapable=data.get("fdeCapable"),
            fdeEnabled=data.get("fdeEnabled"),
            fdeLocked=data.get("fdeLocked"),
            fipsCapable=data.get("fipsCapable"),
            firmwareVersion=data.get("firmwareVersion"),
            hasDegradedChannel=data.get("hasDegradedChannel"),
            hotSpare=data.get("hotSpare"),
            id=data.get("id", "unknown"),
            # interfaceType=data.get("interfaceType"), # Nested object, keep as dict
            # interposerPresent=data.get("interposerPresent"),
            # interposerRef=data.get("interposerRef"),
            invalidDriveData=data.get("invalidDriveData"),
            lowestAlignedLBA=data.get("lowestAlignedLBA"),
            manufacturer=data.get("manufacturer"),
            manufacturerDate=data.get("manufacturerDate"),
            maxSpeed=data.get("maxSpeed"),
            mirrorDrive=data.get("mirrorDrive"),
            nonRedundantAccess=data.get("nonRedundantAccess"),
            offline=data.get("offline"),
            # pfa=data.get("pfa"),
            # pfaReason=data.get("pfaReason"),
            phyDriveType=data.get("phyDriveType"),
            # phyDriveTypeData=data.get("phyDriveTypeData"), # Nested object, keep as dict
            physicalLocation=DriveConfigPhysicalLocation.from_dict(data.get("physicalLocation") or {}),
            productID=data.get("productID"),
            rawCapacity=safe_int(data.get("rawCapacity")),
            sanitizeCapable=data.get("sanitizeCapable"),
            serialNumber=data.get("serialNumber"),
            softwareVersion=data.get("softwareVersion"),
            sparedForDriveRef=data.get("sparedForDriveRef"),
            spindleSpeed=safe_int(data.get("spindleSpeed")),
            ssdWearLife=DriveConfigSsdWearLife.from_dict(data.get("ssdWearLife") or {}) if data.get("ssdWearLife") else None,
            status=data.get("status"),
            uncertified=data.get("uncertified"),
            usableCapacity=data.get("usableCapacity"),
            volumeGroupIndex=safe_int(data.get("volumeGroupIndex")),
            workingChannel=safe_int(data.get("workingChannel")),
            worldWideName=data.get("worldWideName"),
            _raw_data=data.copy()
    )
    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class VolumeConfig(BaseModel):
    """Configuration data for volume"""
    action: Optional[str] = None
    allocGranularity: Optional[int] = None
    applicationTagOwned: Optional[bool] = None
    asyncMirrorSource: Optional[bool] = None
    asyncMirrorTarget: Optional[bool] = None
    blkSize: Optional[int] = None
    blkSizePhysical: Optional[int] = None
    cache: Optional[Dict] = None
    cacheMirroringValidateProtectionInformation: Optional[bool] = None
    cachePoolID: Optional[int] = None
    cacheSettings: Optional[Dict] = None
    capacity: Optional[int] = None
    currentControllerId: Optional[str] = None
    currentManager: Optional[str] = None
    dataAssurance: Optional[bool] = None
    dataDriveCount: Optional[int] = None
    diskPool: Optional[bool] = None
    dssMaxSegmentSize: Optional[int] = None
    dssPreallocEnabled: Optional[bool] = None
    expectedProtectionInformationAppTag: Optional[int] = None
    extendedUniqueIdentifier: Optional[str] = None
    extremeProtection: Optional[bool] = None
    flashCached: Optional[bool] = None
    hostUnmapEnabled: Optional[bool] = None
    id: Optional[str] = None
    increasingBy: Optional[int] = None
    label: Optional[str] = None
    listOfMappings: Optional[List[Dict]] = None
    mapped: Optional[bool] = None
    mediaScan: Optional[Dict] = None
    metadata: Optional[List[Dict]] = None
    mgmtClientAttribute: Optional[int] = None
    name: Optional[str] = None
    objectType: Optional[str] = None
    offline: Optional[bool] = None
    onlineVolumeCopy: Optional[bool] = None
    parityDriveCount: Optional[int] = None
    perms: Optional[Dict] = None
    pitBaseVolume: Optional[bool] = None
    preReadRedundancyCheckEnabled: Optional[bool] = None
    preferredControllerId: Optional[str] = None
    preferredManager: Optional[str] = None
    protectionInformationCapable: Optional[bool] = None
    protectionType: Optional[str] = None
    raidLevel: Optional[str] = None
    reconPriority: Optional[int] = None
    remoteMirrorSource: Optional[bool] = None
    remoteMirrorTarget: Optional[bool] = None
    repairedBlockCount: Optional[int] = None
    sectorOffset: Optional[int] = None
    segmentSize: Optional[int] = None
    status: Optional[str] = None
    thinProvisioned: Optional[bool] = None
    totalSizeInBytes: Optional[int] = None
    volumeCopySource: Optional[bool] = None
    volumeCopyTarget: Optional[bool] = None
    volumeFull: Optional[bool] = None
    volumeGroupRef: Optional[str] = None
    volumeHandle: Optional[int] = None
    volumeRef: Optional[str] = None
    volumeUse: Optional[str] = None
    worldWideName: Optional[str] = None
    wwn: Optional[str] = None
    # Add fields from schema.md that have high occurrence rates
    _raw_data: Dict[str, Any] = field(default_factory=dict)
    
    @staticmethod
    def from_api_response(data: Dict) -> 'VolumeConfig':
        """Create a VolumeConfig instance from API response data"""
        # Explicit capacity conversion to ensure it's an integer
        capacity_value = None
        capacity_raw = data.get("capacity")
        if capacity_raw is not None:
            try:
                capacity_value = int(capacity_raw)
            except (ValueError, TypeError):
                # Handle conversion errors - keep as None
                capacity_value = None
        
        return VolumeConfig(
            action=data.get("action"),
            allocGranularity=safe_int(data.get("allocGranularity")),
            applicationTagOwned=data.get("applicationTagOwned"),
            asyncMirrorSource=data.get("asyncMirrorSource"),
            asyncMirrorTarget=data.get("asyncMirrorTarget"),
            blkSize=safe_int(data.get("blkSize")),
            blkSizePhysical=safe_int(data.get("blkSizePhysical")),
            # cache=data.get("cache"),
            cacheMirroringValidateProtectionInformation=data.get("cacheMirroringValidateProtectionInformation"),
            # cachePoolID=data.get("cachePoolID"),
            cacheSettings=data.get("cacheSettings"), # Nested object, keep as dict
            capacity=capacity_value,
            currentControllerId=data.get("currentControllerId"),
            # currentManager=data.get("currentManager"),
            dataAssurance=data.get("dataAssurance"),
            dataDriveCount=data.get("dataDriveCount"),
            diskPool=data.get("diskPool"),
            dssMaxSegmentSize=safe_int(data.get("dssMaxSegmentSize")),
            dssPreallocEnabled=data.get("dssPreallocEnabled"),
            # expectedProtectionInformationAppTag=data.get("expectedProtectionInformationAppTag"),
            # extendedUniqueIdentifier=data.get("extendedUniqueIdentifier"),
            # extremeProtection=data.get("extremeProtection"),
            flashCached=data.get("flashCached"),
            hostUnmapEnabled=data.get("hostUnmapEnabled"),
            id=data.get("id", "unknown"),
            increasingBy=safe_int(data.get("increasingBy")),
            label=data.get("label"),
            listOfMappings=data.get("listOfMappings"), # List of nested objects, keep as list of dicts
            mapped=data.get("mapped"),
            mediaScan=data.get("mediaScan"), # Nested object, keep as dict
            metadata=data.get("metadata"), # List of nested objects, keep as list of dicts
            mgmtClientAttribute=data.get("mgmtClientAttribute"),
            name=data.get("name"),
            objectType=data.get("objectType"),
            offline=data.get("offline"),
            onlineVolumeCopy=data.get("onlineVolumeCopy"),
            parityDriveCount=safe_int(data.get("parityDriveCount")),
            # perms=data.get("perms"), # Nested object, keep as dict. Replication directions, relationships
            pitBaseVolume=data.get("pitBaseVolume"),
            preReadRedundancyCheckEnabled=data.get("preReadRedundancyCheckEnabled"),
            preferredControllerId=data.get("preferredControllerId"),
            preferredManager=data.get("preferredManager"),
            protectionInformationCapable=data.get("protectionInformationCapable"),
            protectionType=data.get("protectionType"),
            raidLevel=data.get("raidLevel"),
            reconPriority=safe_int(data.get("reconPriority")),
            remoteMirrorSource=data.get("remoteMirrorSource"),
            remoteMirrorTarget=data.get("remoteMirrorTarget"),
            repairedBlockCount=data.get("repairedBlockCount"),
            sectorOffset=safe_int(data.get("sectorOffset")),
            segmentSize=safe_int(data.get("segmentSize")),
            status=data.get("status"),
            thinProvisioned=data.get("thinProvisioned"),
            totalSizeInBytes=safe_int(data.get("totalSizeInBytes")),
            volumeCopySource=data.get("volumeCopySource"),
            volumeCopyTarget=data.get("volumeCopyTarget"),
            volumeFull=data.get("volumeFull"),
            volumeGroupRef=data.get("volumeGroupRef"),
            volumeHandle=safe_int(data.get("volumeHandle")),
            volumeRef=data.get("volumeRef"),
            volumeUse=data.get("volumeUse"),
            worldWideName=data.get("worldWideName"),
            wwn=data.get("wwn"),
            _raw_data=data.copy()
        )
    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class VolumeCGMembersConfig(BaseModel):
    """Configuration data for volume consistency group members"""
    autoDeleteLimit: Optional[int] = None
    autoDeleteSnapshots: Optional[bool] = None
    baseVolumeName: Optional[str] = None
    clusterSize: Optional[int] = None
    consistencyGroupId: Optional[str] = None
    fullWarnThreshold: Optional[int] = None
    pitGroupId: Optional[str] = None
    repositoryVolume: Optional[str] = None
    totalRepositoryCapacity: Optional[int] = None
    totalRepositoryVolumes: Optional[int] = None
    totalSnapshotImages: Optional[int] = None
    totalSnapshotVolumes: Optional[int] = None
    usedRepositoryCapacity: Optional[int] = None
    volumeId: Optional[str] = None
    volumeWwn: Optional[str] = None 
    _raw_data: Dict[str, Any] = field(default_factory=dict)
    # Add fields from schema.md that have high occurrence rates
    
    # Static method to create from API response
    @staticmethod
    def from_api_response(data: Dict) -> 'VolumeCGMembersConfig':
        """Create a VolumeCGMembersConfig instance from API response data"""
        return VolumeCGMembersConfig(
            autoDeleteLimit=safe_int(data.get("autoDeleteLimit")),
            autoDeleteSnapshots=data.get("autoDeleteSnapshots"),
            baseVolumeName=data.get("baseVolumeName"),
            clusterSize=safe_int(data.get("clusterSize")),
            consistencyGroupId=data.get("consistencyGroupId"),
            fullWarnThreshold=safe_int(data.get("fullWarnThreshold")),
            pitGroupId=data.get("pitGroupId"),
            repositoryVolume=data.get("repositoryVolume"),
            totalRepositoryCapacity=safe_int(data.get("totalRepositoryCapacity")),
            totalRepositoryVolumes=safe_int(data.get("totalRepositoryVolumes")),
            totalSnapshotImages=safe_int(data.get("totalSnapshotImages")),
            totalSnapshotVolumes=safe_int(data.get("totalSnapshotVolumes")),
            usedRepositoryCapacity=safe_int(data.get("usedRepositoryCapacity")),
            volumeId=data.get("volumeId", "unknown"),
            volumeWwn=data.get("volumeWwn")
        )
    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)
    
@dataclass
class InterfaceConfigInterfaceTypeData(BaseModel):
    """Interface type data for InterfaceConfig"""
    sas: Optional[Dict[str, Any]] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)
    
    @staticmethod
    def from_api_response(data: Dict) -> 'InterfaceConfigInterfaceTypeData':
        """Create an InterfaceConfigInterfaceTypeData instance from API response data"""
        return InterfaceConfigInterfaceTypeData(
            sas=data.get("sas"),
            _raw_data=data.copy()
        )
    
    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class InterfaceConfig(BaseModel):
    """Configuration data for interfaces"""
    # channelPortRef: Optional[str] = None
    # channelPortRefs: Optional[List[Any]] = None
    channelType: Optional[str] = None
    # commandProtocolPropertiesList: Optional[Dict] = None
    controllerRef: Optional[str] = None
    interfaceRef: Optional[str] = None
    ioInterfaceTypeData: Optional[InterfaceConfigInterfaceTypeData] = None

    # Add fields from schema.md that have high occurrence rates
    _raw_data: Dict[str, Any] = field(default_factory=dict)
    
    # Static method to create from API response
    @staticmethod
    def from_api_response(data: Dict) -> 'InterfaceConfig':
        """Create an InterfaceConfig instance from API response data"""
        io_interface_data = None
        if data.get("ioInterfaceTypeData"):
            io_interface_data = InterfaceConfigInterfaceTypeData.from_api_response(data["ioInterfaceTypeData"])
            
        return InterfaceConfig(
            # channelPortRef=data.get("channelPortRef"),
            # channelPortRefs=data.get("channelPortRefs"),
            channelType=data.get("channelType"),
            # commandProtocolPropertiesList=data.get("commandProtocolPropertiesList"),
            controllerRef=data.get("controllerRef"),
            interfaceRef=data.get("interfaceRef"),
            ioInterfaceTypeData=io_interface_data,
            _raw_data=data.copy()
        )
    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)
    
@dataclass
class TrayConfig(BaseModel):
    partNumber: Optional[str] = None
    serialNumber: Optional[str] = None
    id: Optional[str] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)
    # Add fields from schema.md that have high occurrence rates

    @staticmethod
    def from_api_response(data: Dict) -> 'TrayConfig':
        return TrayConfig(
            id=data.get('id', 'unknown'),
            partNumber=data.get('partNumber'),
            serialNumber=data.get('serialNumber'),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class LockdownStatusConfig(BaseModel):
    """Configuration data for lockdown status"""
    id: Optional[str] = None
    lockdownState: Optional[str] = None
    unlockKeyId: Optional[str] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'LockdownStatusConfig':
        return LockdownStatusConfig(
            id=data.get('id', 'unknown'),
            lockdownState=data.get('lockdownState'),
            unlockKeyId=data.get('unlockKeyId'),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass 
class StoragePoolConfigVolumeGroupDataDiskPoolData:
    """Configuration data for StoragePoolConfig Volume Group Data Disk Pool Data
    {'reconstructionReservedDriveCount': 2, 'reconstructionReservedAmt': '1583769190400', 
    'reconstructionReservedDriveCountCurrent': 3, 'poolUtilizationWarningThreshold': 0, 
    'poolUtilizationCriticalThreshold': 85, 'poolUtilizationState': 'utilizationOptimal', 
    'unusableCapacity': '0', 'degradedReconstructPriority': 'medium', 
    'criticalReconstructPriority': 'high', 'backgroundOperationPriority': 'low',  
    'allocGranularity': '4294967296', 'minimumDriveCount': 11, 'poolVersion': 0}   
 
    """
    allocGranularity: Optional[int] = None
    backgroundOperationPriority: Optional[str] = None
    criticalReconstructPriority: Optional[str] = None
    degradedReconstructPriority: Optional[str] = None
    minimumDriveCount: Optional[int] = None
    poolUtilizationWarningThreshold: Optional[int] = None
    poolUtilizationCriticalThreshold: Optional[int] = None
    poolUtilizationState: Optional[str] = None
    poolVersion: Optional[int] = None
    reconstructionReservedDriveCount: Optional[int] = None
    reconstructionReservedAmt: Optional[int] = None   # string integer
    reconstructionReservedDriveCountCurrent: Optional[int] = None
    unusableCapacity: Optional[int] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

    @staticmethod
    def from_dict(data: Dict) -> 'StoragePoolConfigVolumeGroupDataDiskPoolData':
        if not data:
            return StoragePoolConfigVolumeGroupDataDiskPoolData(_raw_data={})
        
        return StoragePoolConfigVolumeGroupDataDiskPoolData(
            allocGranularity=safe_int(data.get('allocGranularity')),
            backgroundOperationPriority=data.get('backgroundOperationPriority'),
            criticalReconstructPriority=data.get('criticalReconstructPriority'),
            degradedReconstructPriority=data.get('degradedReconstructPriority'),
            minimumDriveCount=safe_int(data.get('minimumDriveCount')),
            poolUtilizationWarningThreshold=safe_int(data.get('poolUtilizationWarningThreshold')),
            poolUtilizationCriticalThreshold=safe_int(data.get('poolUtilizationCriticalThreshold')),
            poolUtilizationState=data.get('poolUtilizationState'),
            poolVersion=safe_int(data.get('poolVersion')),
            reconstructionReservedDriveCount=safe_int(data.get('reconstructionReservedDriveCount')),
            reconstructionReservedAmt=safe_int(data.get('reconstructionReservedAmt')),
            reconstructionReservedDriveCountCurrent=safe_int(data.get('reconstructionReservedDriveCountCurrent')),
            unusableCapacity=safe_int(data.get('unusableCapacity')),
            _raw_data=data
        )


@dataclass
class StoragePoolConfigVolumeGroupData:
    """Configuration data for StoragePoolConfig Volume Group Data
    {'type': 'diskPool', 'diskPoolData': {'reconstructionReservedDriveCount': 2, 'reconstructionReservedAmt':
   '1583769190400', 'reconstructionReservedDriveCountCurrent': 3, 'poolUtilizationWarningThreshold': 0, 
   'poolUtilizationCriticalThreshold': 85, 'poolUtilizationState': 'utilizationOptimal', 'unusableCapacity': '0', 
   'degradedReconstructPriority': 'medium', 'criticalReconstructPriority': 'high', 'backgroundOperationPriority': 'low',  
   'allocGranularity': '4294967296', 'minimumDriveCount': 11, 'poolVersion': 0}}   
 
    """
    # Add fields from schema.md that have high occurrence rates
    type: Optional[str] = None
    diskPoolData: Optional[StoragePoolConfigVolumeGroupDataDiskPoolData] = None    
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'StoragePoolConfigVolumeGroupData':
        if not data:
            return StoragePoolConfigVolumeGroupData(_raw_data={})
        
        disk_pool_data = data.get('diskPoolData')
        return StoragePoolConfigVolumeGroupData(
            type=data.get('type'),
            diskPoolData=StoragePoolConfigVolumeGroupDataDiskPoolData.from_dict(disk_pool_data) if disk_pool_data else None,
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class StoragePoolConfig(BaseModel):
    """Configuration data for storagepoolconfig"""
    id: Optional[str] = None
    blkSizeRecommended: Optional[int] = None
    blkSizeSupported: Optional[List[int]] = None
    diskPool: Optional[bool] = None
    drawerLossProtection: Optional[bool] = None
    driveBlockFormat: Optional[str] = None
    driveMediaType: Optional[str] = None
    drivePhysicalType: Optional[str] = None
    dulbeEnabled: Optional[bool] = None
    # extents: Optional[List[Dict]] = None
    freeSpace: Optional[int] = None
    isInaccessible: Optional[bool] = None
    label: Optional[str] = None
    name: Optional[str] = None
    normalizedSpindleSpeed: Optional[str] = None
    offline: Optional[bool] = None
    # protectionInformationCapabilities: Optional[Dict] = None
    # protectionInformationCapable: Optional[bool] = None
    raidLevel: Optional[str] = None
    raidStatus: Optional[str] = None
    reserved1: Optional[str] = None
    reserved2: Optional[str] = None
    reservedSpaceAllocated: Optional[bool] = None
    securityLevel: Optional[str] = None
    securityType: Optional[str] = None
    sequenceNum: Optional[int] = None
    spindleSpeed: Optional[int] = None
    spindleSpeedMatch: Optional[bool] = None
    state: Optional[str] = None
    totalRaidedSpace: Optional[int] = None
    trayLossProtection: Optional[bool] = None
    usage: Optional[str] = None
    usedSpace: Optional[int] = None
    volumeGroupData: Optional[StoragePoolConfigVolumeGroupData] = None
    volumeGroupRef: Optional[str] = None
    worldWideName: Optional[str] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'StoragePoolConfig':
        return StoragePoolConfig(
            blkSizeRecommended=safe_int(data.get('blkSizeRecommended')),
            blkSizeSupported=data.get('blkSizeSupported'),
            diskPool=data.get('diskPool'),
            drawerLossProtection=data.get('drawerLossProtection'),
            driveBlockFormat=data.get('driveBlockFormat'),
            driveMediaType=data.get('driveMediaType'),
            drivePhysicalType=data.get('drivePhysicalType'),
            dulbeEnabled=data.get('dulbeEnabled'),
            # extents=data.get('extents'),
            freeSpace=safe_int(data.get('freeSpace')),
            id=data.get('id', 'unknown'),
            isInaccessible=data.get('isInaccessible'),
            label=data.get('label'),
            name=data.get('name'),
            normalizedSpindleSpeed=data.get('normalizedSpindleSpeed'),
            offline=data.get('offline'),
            # protectionInformationCapabilities=data.get('protectionInformationCapabilities'),
            # protectionInformationCapable=data.get('protectionInformationCapable'),
            raidLevel=data.get('raidLevel'),
            raidStatus=data.get('raidStatus'),
            reserved1=data.get('reserved1'),
            reserved2=data.get('reserved2'),
            reservedSpaceAllocated=data.get('reservedSpaceAllocated'),
            securityLevel=data.get('securityLevel'),
            securityType=data.get('securityType'),
            sequenceNum=safe_int(data.get('sequenceNum')),
            spindleSpeed=safe_int(data.get('spindleSpeed')),
            spindleSpeedMatch=data.get('spindleSpeedMatch'),
            state=data.get('state'),
            totalRaidedSpace=safe_int(data.get('totalRaidedSpace')),
            trayLossProtection=data.get('trayLossProtection'),
            usage=data.get('usage'),
            usedSpace=safe_int(data.get('usedSpace')),
            volumeGroupData=StoragePoolConfigVolumeGroupData.from_api_response(data.get('volumeGroupData', {})),
            volumeGroupRef=data.get('volumeGroupRef'),
            worldWideName=data.get('worldWideName'),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)


@dataclass
class VolumeMappingsConfig(BaseModel):
    """Configuration data for VolumeMappings Config"""
    lun: Optional[int] = None
    lunMappingRef: Optional[str] = None
    mapRef: Optional[str] = None
    type: Optional[str] = None
    volumeRef: Optional[str] = None
    id: Optional[str] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'VolumeMappingsConfig':
        return VolumeMappingsConfig(
            id=data.get('id', 'unknown'),
            lun=safe_int(data.get('lun')),
            lunMappingRef=data.get('lunMappingRef'),
            mapRef=data.get('mapRef'),
            type=data.get('type'),
            volumeRef=data.get('volumeRef'),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class AnalysedVolumeStatistics(BaseModel):
    """Configuration data for analysedvolume statistics"""    
    averageQueueDepth: Optional[float] = None
    averageReadOpSize: Optional[float] = None
    averageWriteOpSize: Optional[float] = None
    cacheWriteWaitBytesPercent: Optional[float] = None
    cacheWriteWaitOpsPercent: Optional[float] = None
    combinedHitResponseTime: Optional[float] = None
    combinedHitResponseTimeStdDev: Optional[float] = None
    combinedIOps: Optional[float] = None
    combinedResponseTime: Optional[float] = None
    combinedResponseTimeStdDev: Optional[float] = None
    combinedThroughput: Optional[float] = None
    controllerId: Optional[str] = None
    flashCacheHitPct: Optional[float] = None
    flashCacheReadHitBytes: Optional[float] = None
    flashCacheReadHitOps: Optional[float] = None
    flashCacheReadResponseTime: Optional[float] = None
    flashCacheReadThroughput: Optional[float] = None
    fullStripeWritesBytesPercent: Optional[float] = None
    mapped: Optional[bool] = None
    observedTime: Optional[str] = None          # ISO 8601 date-time string
    observedTimeInMS: Optional[str] = None      # string integer
    otherIOps: Optional[float] = None
    poolId: Optional[str] = None
    prefetchHitPercent: Optional[float] = None
    queueDepthMax: Optional[float] = None
    queueDepthTotal: Optional[float] = None
    randomBytesPercent: Optional[float] = None
    randomIosPercent: Optional[float] = None
    readCacheUtilization: Optional[float] = None
    readHitBytes: Optional[float] = None
    readHitOps: Optional[float] = None
    readHitResponseTime: Optional[float] = None
    readHitResponseTimeStdDev: Optional[float] = None
    readIOps: Optional[float] = None
    readOps: Optional[float] = None
    readPhysicalIOps: Optional[float] = None
    readResponseTime: Optional[float] = None
    readResponseTimeStdDev: Optional[float] = None
    readThroughput: Optional[float] = None
    readTimeMax: Optional[float] = None
    sourceController: Optional[str] = None
    volumeId: Optional[str] = None
    volumeName: Optional[str] = None
    workLoadId: Optional[str] = None                # ex: 4200000009000000000000000000000000000000
    writeCacheUtilization: Optional[float] = None
    writeHitBytes: Optional[float] = None
    writeHitOps: Optional[float] = None
    writeHitResponseTime: Optional[float] = None
    writeHitResponseTimeStdDev: Optional[float] = None
    writeIOps: Optional[float] = None
    writeOps: Optional[float] = None
    writePhysicalIOps: Optional[float] = None
    writeResponseTime: Optional[float] = None
    writeResponseTimeStdDev: Optional[float] = None
    writeThroughput: Optional[float] = None
    writeTimeMax: Optional[float] = None    
    # Enriched fields added during processing
    host: Optional[str] = None
    host_group: Optional[str] = None
    storage_pool: Optional[str] = None
    storage_system_name: Optional[str] = None
    storage_system_wwn: Optional[str] = None
    storageSystemName: Optional[str] = None
    storageSystemWWN: Optional[str] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'AnalysedVolumeStatistics':
        # observedTimeInMS comes as string from API, keep as string
        observed_time_ms = data.get('observedTimeInMS')
        return AnalysedVolumeStatistics(
            averageQueueDepth=data.get('averageQueueDepth'),
            averageReadOpSize=data.get('averageReadOpSize'),
            averageWriteOpSize=data.get('averageWriteOpSize'),
            cacheWriteWaitBytesPercent=data.get('cacheWriteWaitBytesPercent'),
            cacheWriteWaitOpsPercent=data.get('cacheWriteWaitOpsPercent'),
            combinedHitResponseTime=data.get('combinedHitResponseTime'),
            combinedHitResponseTimeStdDev=data.get('combinedHitResponseTimeStdDev'),
            combinedIOps=data.get('combinedIOps'),
            combinedResponseTime=data.get('combinedResponseTime'),
            combinedResponseTimeStdDev=data.get('combinedResponseTimeStdDev'),
            combinedThroughput=data.get('combinedThroughput'),
            controllerId=data.get('controllerId'),
            flashCacheHitPct=data.get('flashCacheHitPct'),
            flashCacheReadHitBytes=data.get('flashCacheReadHitBytes'),
            flashCacheReadHitOps=data.get('flashCacheReadHitOps'),
            flashCacheReadResponseTime=data.get('flashCacheReadResponseTime'),
            flashCacheReadThroughput=data.get('flashCacheReadThroughput'),
            fullStripeWritesBytesPercent=data.get('fullStripeWritesBytesPercent'),
            mapped=data.get('mapped'),
            observedTime=data.get('observedTime'),
            observedTimeInMS=str(observed_time_ms) if observed_time_ms is not None else None,
            otherIOps=data.get('otherIOps'),
            poolId=data.get('poolId'),
            prefetchHitPercent=data.get('prefetchHitPercent'),
            queueDepthMax=data.get('queueDepthMax'),
            queueDepthTotal=data.get('queueDepthTotal'),
            randomBytesPercent=data.get('randomBytesPercent'),
            randomIosPercent=data.get('randomIosPercent'),
            readCacheUtilization=data.get('readCacheUtilization'),
            readHitBytes=data.get('readHitBytes'),
            readHitOps=data.get('readHitOps'),
            readHitResponseTime=data.get('readHitResponseTime'),
            readHitResponseTimeStdDev=data.get('readHitResponseTimeStdDev'),
            readIOps=data.get('readIOps'),
            readOps=data.get('readOps'),
            readPhysicalIOps=data.get('readPhysicalIOps'),
            readResponseTime=data.get('readResponseTime'),
            readResponseTimeStdDev=data.get('readResponseTimeStdDev'),
            readThroughput=data.get('readThroughput'),
            readTimeMax=data.get('readTimeMax'),
            sourceController=data.get('sourceController'),
            volumeId=data.get('volumeId'),
            volumeName=data.get('volumeName'),
            workLoadId=data.get('workLoadId'),
            writeCacheUtilization=data.get('writeCacheUtilization'),
            writeHitBytes=data.get('writeHitBytes'),
            writeHitOps=data.get('writeHitOps'),
            writeHitResponseTime=data.get('writeHitResponseTime'),
            writeHitResponseTimeStdDev=data.get('writeHitResponseTimeStdDev'),
            writeIOps=data.get('writeIOps'),
            writeOps=data.get('writeOps'),
            writePhysicalIOps=data.get('writePhysicalIOps'),
            writeResponseTime=data.get('writeResponseTime'),
            writeResponseTimeStdDev=data.get('writeResponseTimeStdDev'),
            writeThroughput=data.get('writeThroughput'),
            writeTimeMax=data.get('writeTimeMax'),
            # Enriched fields
            host=data.get('host'),
            host_group=data.get('host_group'),
            storage_pool=data.get('storage_pool'),
            storage_system_name=data.get('storage_system_name'),
            storage_system_wwn=data.get('storage_system_wwn'),
            storageSystemName=data.get('storageSystemName') or data.get('storage_system_name'),
            storageSystemWWN=data.get('storageSystemWWN') or data.get('storage_system_wwn'),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class AnalysedDriveStatistics(BaseModel):
    """Configuration data for Analysed Drive Statistics"""    
    averageQueueDepth: Optional[float] = None
    averageReadOpSize: Optional[float] = None
    averageWriteOpSize: Optional[float] = None
    combinedIOps: Optional[float] = None
    combinedResponseTime: Optional[float] = None
    combinedResponseTimeStdDev: Optional[float] = None
    combinedThroughput: Optional[float] = None
    diskId: Optional[str] = None
    driveSlot: Optional[int] = None
    observedTime: Optional[str] = None                  # ISO 8601 date-time string
    observedTimeInMS: Optional[str] = None              # string integer  
    otherIOps: Optional[float] = None
    queueDepthMax: Optional[float] = None
    randomBytesPercent: Optional[float] = None
    randomIosPercent: Optional[float] = None
    readIOps: Optional[float] = None
    readOps: Optional[float] = None
    readPhysicalIOps: Optional[float] = None
    readResponseTime: Optional[float] = None
    readResponseTimeStdDev: Optional[float] = None
    readThroughput: Optional[float] = None
    readTimeMax: Optional[float] = None
    sourceController: Optional[str] = None
    trayId: Optional[int] = None
    trayRef: Optional[str] = None
    volGroupId: Optional[str] = None
    volGroupName: Optional[str] = None
    writeIOps: Optional[float] = None
    writeOps: Optional[float] = None
    writePhysicalIOps: Optional[float] = None
    writeResponseTime: Optional[float] = None
    writeResponseTimeStdDev: Optional[float] = None
    writeThroughput: Optional[float] = None
    writeTimeMax: Optional[float] = None
    # Enriched fields added during processing
    tray_id: Optional[str] = None
    vol_group_name: Optional[str] = None
    has_degraded_channel: Optional[bool] = None
    system_name: Optional[str] = None
    system_wwn: Optional[str] = None
    system_id: Optional[str] = None
    system_model: Optional[str] = None
    system_firmware_version: Optional[str] = None
    drive_slot: Optional[str] = None
    tray_ref: Optional[str] = None
    storageSystemName: Optional[str] = None
    storageSystemWWN: Optional[str] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'AnalysedDriveStatistics':
        observed_time_ms = None
        observed_time_in_ms_value = data.get('observedTimeInMS')
        if observed_time_in_ms_value is not None:
            try:
                observed_time_ms = int(observed_time_in_ms_value)
            except (ValueError, TypeError):
                # Handle conversion errors
                observed_time_ms = None
        return AnalysedDriveStatistics(
            averageQueueDepth=data.get('averageQueueDepth'),
            averageReadOpSize=data.get('averageReadOpSize'),
            averageWriteOpSize=data.get('averageWriteOpSize'),
            combinedIOps=data.get('combinedIOps'),
            combinedResponseTime=data.get('combinedResponseTime'),
            combinedResponseTimeStdDev=data.get('combinedResponseTimeStdDev'),
            combinedThroughput=data.get('combinedThroughput'),
            diskId=data.get('diskId', 'unknown'),
            driveSlot=safe_int(data.get('driveSlot')),
            observedTime=data.get('observedTime'),
            observedTimeInMS=str(observed_time_ms) if observed_time_ms is not None else None,
            otherIOps=data.get('otherIOps'),
            queueDepthMax=data.get('queueDepthMax'),
            randomBytesPercent=data.get('randomBytesPercent'),
            randomIosPercent=data.get('randomIosPercent'),
            readIOps=data.get('readIOps'),
            readOps=data.get('readOps'),
            readPhysicalIOps=data.get('readPhysicalIOps'),
            readResponseTime=data.get('readResponseTime'),
            readResponseTimeStdDev=data.get('readResponseTimeStdDev'),
            readThroughput=data.get('readThroughput'),
            readTimeMax=data.get('readTimeMax'),
            sourceController=data.get('sourceController'),
            trayId=safe_int(data.get('trayId')),
            trayRef=data.get('trayRef'),
            volGroupId=data.get('volGroupId'),
            volGroupName=data.get('volGroupName'),
            writeIOps=data.get('writeIOps'),
            writeOps=data.get('writeOps'),
            writePhysicalIOps=data.get('writePhysicalIOps'),
            writeResponseTime=data.get('writeResponseTime'),
            writeResponseTimeStdDev=data.get('writeResponseTimeStdDev'),
            writeThroughput=data.get('writeThroughput'),
            writeTimeMax=data.get('writeTimeMax'),
            # Enriched fields
            tray_id=data.get('tray_id'),
            vol_group_name=data.get('vol_group_name'),
            has_degraded_channel=data.get('has_degraded_channel'),
            system_name=data.get('system_name'),
            system_wwn=data.get('system_wwn'),
            system_id=data.get('system_id'),
            system_model=data.get('system_model'),
            system_firmware_version=data.get('system_firmware_version'),
            drive_slot=data.get('drive_slot'),
            tray_ref=data.get('tray_ref'),
            storageSystemName=data.get('storageSystemName') or data.get('storage_system_name'),
            storageSystemWWN=data.get('storageSystemWWN') or data.get('storage_system_wwn'),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class AnalysedSystemStatistics(BaseModel):
    """Configuration data for Analysed System Statistics"""
    averageReadOpSize: Optional[float] = None
    averageWriteOpSize: Optional[float] = None
    cacheHitBytesPercent: Optional[float] = None
    combinedHitResponseTime: Optional[float] = None
    combinedHitResponseTimeStdDev: Optional[float] = None
    combinedIOps: Optional[float] = None
    combinedResponseTime: Optional[float] = None
    combinedResponseTimeStdDev: Optional[float] = None
    combinedThroughput: Optional[float] = None
    cpuAvgUtilization: Optional[float] = None
    ddpBytesPercent: Optional[float] = None
    fullStripeWritesBytesPercent: Optional[float] = None
    maxCpuUtilization: Optional[float] = None
    maxPossibleBpsUnderCurrentLoad: Optional[float] = None
    maxPossibleIopsUnderCurrentLoad: Optional[float] = None
    mirrorBytesPercent: Optional[float] = None
    observedTime: Optional[str] = None          # ISO 8601 date-time string     
    observedTimeInMS: Optional[str] = None      # string integer
    otherIOps: Optional[float] = None
    raid0BytesPercent: Optional[float] = None
    raid1BytesPercent: Optional[float] = None
    raid5BytesPercent: Optional[float] = None
    raid6BytesPercent: Optional[float] = None
    randomIosPercent: Optional[float] = None
    readHitResponseTime: Optional[float] = None
    readHitResponseTimeStdDev: Optional[float] = None
    readIOps: Optional[float] = None
    readOps: Optional[float] = None
    readPhysicalIOps: Optional[float] = None
    readResponseTime: Optional[float] = None
    readResponseTimeStdDev: Optional[float] = None
    readThroughput: Optional[float] = None
    sourceController: Optional[str] = None
    # storageSystemId: Optional[str] = None     # garbage field (1, instead of wwn string)
    storageSystemName: Optional[str] = None
    storageSystemWWN: Optional[str] = None
    writeHitResponseTime: Optional[float] = None
    writeHitResponseTimeStdDev: Optional[float] = None
    writeIOps: Optional[float] = None
    writeOps: Optional[float] = None
    writePhysicalIOps: Optional[float] = None
    writeResponseTime: Optional[float] = None
    writeResponseTimeStdDev: Optional[float] = None
    writeThroughput: Optional[float] = None
    # Enriched fields added during processing
    system_id: Optional[str] = None
    system_name: Optional[str] = None
    system_wwn: Optional[str] = None
    system_model: Optional[str] = None
    system_status: Optional[str] = None
    system_sub_model: Optional[str] = None
    firmware_version: Optional[str] = None
    app_version: Optional[str] = None
    boot_version: Optional[str] = None
    nvsram_version: Optional[str] = None
    chassis_serial_number: Optional[str] = None
    drive_count: Optional[int] = None
    tray_count: Optional[int] = None
    hot_spare_count: Optional[int] = None
    used_pool_space: Optional[str] = None
    free_pool_space: Optional[str] = None
    unconfigured_space: Optional[str] = None
    auto_load_balancing_enabled: Optional[bool] = None
    host_connectivity_reporting_enabled: Optional[bool] = None
    remote_mirroring_enabled: Optional[bool] = None
    security_key_enabled: Optional[bool] = None
    simplex_mode_enabled: Optional[bool] = None
    drive_types: Optional[str] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'AnalysedSystemStatistics':
        observed_time_ms = None
        observed_time_in_ms_value = data.get('observedTimeInMS')
        if observed_time_in_ms_value is not None:
            try:
                observed_time_ms = int(observed_time_in_ms_value)
            except (ValueError, TypeError):
                # Handle conversion errors
                observed_time_ms = None
        return AnalysedSystemStatistics(
            averageReadOpSize=data.get('averageReadOpSize'),
            averageWriteOpSize=data.get('averageWriteOpSize'),
            cacheHitBytesPercent=data.get('cacheHitBytesPercent'),
            combinedHitResponseTime=data.get('combinedHitResponseTime'),
            combinedHitResponseTimeStdDev=data.get('combinedHitResponseTimeStdDev'),
            combinedIOps=data.get('combinedIOps'),
            combinedResponseTime=data.get('combinedResponseTime'),
            combinedResponseTimeStdDev=data.get('combinedResponseTimeStdDev'),
            combinedThroughput=data.get('combinedThroughput'),
            cpuAvgUtilization=data.get('cpuAvgUtilization'),
            ddpBytesPercent=data.get('ddpBytesPercent'),
            fullStripeWritesBytesPercent=data.get('fullStripeWritesBytesPercent'),
            maxCpuUtilization=data.get('maxCpuUtilization'),
            maxPossibleBpsUnderCurrentLoad=data.get('maxPossibleBpsUnderCurrentLoad'),
            maxPossibleIopsUnderCurrentLoad=data.get('maxPossibleIopsUnderCurrentLoad'),
            mirrorBytesPercent=data.get('mirrorBytesPercent'),
            observedTime=data.get('observedTime'),
            observedTimeInMS=str(observed_time_ms) if observed_time_ms is not None else None,
            otherIOps=data.get('otherIOps'),
            raid0BytesPercent=data.get('raid0BytesPercent'),
            raid1BytesPercent=data.get('raid1BytesPercent'),
            raid5BytesPercent=data.get('raid5BytesPercent'),
            raid6BytesPercent=data.get('raid6BytesPercent'),
            randomIosPercent=data.get('randomIosPercent'),
            readHitResponseTime=data.get('readHitResponseTime'),
            readHitResponseTimeStdDev=data.get('readHitResponseTimeStdDev'),
            readIOps=data.get('readIOps'),
            readOps=data.get('readOps'),
            readPhysicalIOps=data.get('readPhysicalIOps'),
            readResponseTime=data.get('readResponseTime'),
            readResponseTimeStdDev=data.get('readResponseTimeStdDev'),
            readThroughput=data.get('readThroughput'),
            sourceController=data.get('sourceController'),
            # storageSystemId=data.get('storageSystemId'),
            storageSystemName=data.get('storageSystemName'),
            storageSystemWWN=data.get('storageSystemWWN'),
            writeHitResponseTime=data.get('writeHitResponseTime'),
            writeHitResponseTimeStdDev=data.get('writeHitResponseTimeStdDev'),
            writeIOps=data.get('writeIOps'),
            writeOps=data.get('writeOps'),
            writePhysicalIOps=data.get('writePhysicalIOps'),
            writeResponseTime=data.get('writeResponseTime'),
            writeResponseTimeStdDev=data.get('writeResponseTimeStdDev'),
            writeThroughput=data.get('writeThroughput'),
            # Enriched fields
            system_id=data.get('system_id'),
            system_name=data.get('system_name'),
            system_wwn=data.get('system_wwn'),
            system_model=data.get('system_model'),
            system_status=data.get('system_status'),
            system_sub_model=data.get('system_sub_model'),
            firmware_version=data.get('firmware_version'),
            app_version=data.get('app_version'),
            boot_version=data.get('boot_version'),
            nvsram_version=data.get('nvsram_version'),
            chassis_serial_number=data.get('chassis_serial_number'),
            drive_count=data.get('drive_count'),
            tray_count=data.get('tray_count'),
            hot_spare_count=data.get('hot_spare_count'),
            used_pool_space=data.get('used_pool_space'),
            free_pool_space=data.get('free_pool_space'),
            unconfigured_space=data.get('unconfigured_space'),
            auto_load_balancing_enabled=data.get('auto_load_balancing_enabled'),
            host_connectivity_reporting_enabled=data.get('host_connectivity_reporting_enabled'),
            remote_mirroring_enabled=data.get('remote_mirroring_enabled'),
            security_key_enabled=data.get('security_key_enabled'),
            simplex_mode_enabled=data.get('simplex_mode_enabled'),
            drive_types=data.get('drive_types'),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class AnalysedInterfaceStatistics(BaseModel):
    """Configuration data for Analysed Interface Statistics"""
    averageReadOpSize: Optional[float] = None
    averageWriteOpSize: Optional[float] = None
    channelErrorCounts: Optional[float] = None
    channelNumber: Optional[int] = None
    channelType: Optional[str] = None
    combinedIOps: Optional[float] = None
    combinedResponseTime: Optional[float] = None
    combinedResponseTimeStdDev: Optional[float] = None
    combinedThroughput: Optional[float] = None
    controllerId: Optional[str] = None
    interfaceId: Optional[str] = None
    observedTime: Optional[str] = None      # ISO 8601 date-time string
    observedTimeInMS: Optional[str] = None  # string integer
    otherIOps: Optional[float] = None
    queueDepthMax: Optional[float] = None
    queueDepthTotal: Optional[float] = None
    readIOps: Optional[float] = None
    readOps: Optional[float] = None
    readResponseTime: Optional[float] = None
    readResponseTimeStdDev: Optional[float] = None
    readThroughput: Optional[float] = None
    sourceController: Optional[str] = None
    writeIOps: Optional[float] = None
    writeOps: Optional[float] = None
    writeResponseTime: Optional[float] = None
    writeResponseTimeStdDev: Optional[float] = None
    writeThroughput: Optional[float] = None
    storageSystemName: Optional[str] = None
    storageSystemWWN: Optional[str] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'AnalysedInterfaceStatistics':
        # observedTimeInMS comes as string from API, keep as string
        observed_time_ms = data.get('observedTimeInMS')           
        return AnalysedInterfaceStatistics(
            averageReadOpSize=data.get('averageReadOpSize'),
            averageWriteOpSize=data.get('averageWriteOpSize'),
            channelErrorCounts=data.get('channelErrorCounts'),
            channelNumber=safe_int(data.get('channelNumber')),
            channelType=data.get('channelType'),
            combinedIOps=data.get('combinedIOps'),
            combinedResponseTime=data.get('combinedResponseTime'),
            combinedResponseTimeStdDev=data.get('combinedResponseTimeStdDev'),
            combinedThroughput=data.get('combinedThroughput'),
            controllerId=data.get('controllerId'),
            interfaceId=data.get('interfaceId'),
            observedTime=data.get('observedTime'),
            observedTimeInMS=str(observed_time_ms) if observed_time_ms is not None else None,
            otherIOps=data.get('otherIOps'),
            queueDepthMax=data.get('queueDepthMax'),
            queueDepthTotal=data.get('queueDepthTotal'),
            readIOps=data.get('readIOps'),
            readOps=data.get('readOps'),
            readResponseTime=data.get('readResponseTime'),
            readResponseTimeStdDev=data.get('readResponseTimeStdDev'),
            readThroughput=data.get('readThroughput'),
            sourceController=data.get('sourceController'),
            writeIOps=data.get('writeIOps'),
            writeOps=data.get('writeOps'),
            writeResponseTime=data.get('writeResponseTime'),
            writeResponseTimeStdDev=data.get('writeResponseTimeStdDev'),
            writeThroughput=data.get('writeThroughput'),
            storageSystemName=data.get('storageSystemName') or data.get('storage_system_name'),
            storageSystemWWN=data.get('storageSystemWWN') or data.get('storage_system_wwn'),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)


@dataclass
class AnalyzedControllerStatisticsValues:
    """Configuration data for analyzedcontrollerstatistics details"""
    averageReadOpSize: Optional[float] = None
    averageWriteOpSize: Optional[float] = None
    cacheHitBytesPercent: Optional[float] = None
    combinedHitResponseTime: Optional[float] = None
    combinedHitResponseTimeStdDev: Optional[float] = None
    combinedIOps: Optional[float] = None
    combinedResponseTime: Optional[float] = None
    combinedResponseTimeStdDev: Optional[float] = None
    combinedThroughput: Optional[float] = None
    controllerId: Optional[str] = None
    cpuAvgUtilization: Optional[float] = None
    # cpuAvgUtilizationPerCore: Optional[List[float]] = None       # TMI
    # cpuAvgUtilizationPerCoreStdDev: Optional[List[float]] = None # TMI
    ddpBytesPercent: Optional[float] = None
    fullStripeWritesBytesPercent: Optional[float] = None
    maxCpuUtilization: Optional[float] = None
    # maxCpuUtilizationPerCore: Optional[List[float]] = None       # TMI
    maxPossibleBpsUnderCurrentLoad: Optional[float] = None
    maxPossibleIopsUnderCurrentLoad: Optional[float] = None
    mirrorBytesPercent: Optional[float] = None
    observedTime: Optional[str] = None                        # ISO 8601 date-time string
    observedTimeInMS: Optional[str] = None                    # Milliseconds since epoch
    otherIOps: Optional[float] = None
    raid0BytesPercent: Optional[float] = None
    raid1BytesPercent: Optional[float] = None
    raid5BytesPercent: Optional[float] = None
    raid6BytesPercent: Optional[float] = None
    randomIosPercent: Optional[float] = None
    readHitResponseTime: Optional[float] = None
    readHitResponseTimeStdDev: Optional[float] = None
    readIOps: Optional[float] = None
    readOps: Optional[float] = None
    readPhysicalIOps: Optional[float] = None
    readResponseTime: Optional[float] = None
    readResponseTimeStdDev: Optional[float] = None
    readThroughput: Optional[float] = None
    sourceController: Optional[str] = None
    writeHitResponseTime: Optional[float] = None
    writeHitResponseTimeStdDev: Optional[float] = None
    writeIOps: Optional[float] = None
    writeOps: Optional[float] = None
    writePhysicalIOps: Optional[float] = None
    writeResponseTime: Optional[float] = None
    writeResponseTimeStdDev: Optional[float] = None
    writeThroughput: Optional[float] = None
    # Enriched fields added during processing
    controller_id: Optional[str] = None
    controller_label: Optional[str] = None
    controller_active: Optional[bool] = None
    controller_model: Optional[str] = None
    interface_type: Optional[str] = None
    is_management_interface: Optional[bool] = None
    system_name: Optional[str] = None
    system_wwn: Optional[str] = None
    system_id: Optional[str] = None
    system_model: Optional[str] = None
    system_firmware_version: Optional[str] = None
    link_state: Optional[str] = None
    current_speed: Optional[str] = None
    link_width: Optional[str] = None
    port_state: Optional[str] = None
    channel: Optional[str] = None
    storageSystemName: Optional[str] = None
    storageSystemWWN: Optional[str] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: Dict) -> 'AnalyzedControllerStatisticsValues':
        observed_time_ms = None
        observed_time_in_ms_value = data.get('observedTimeInMS')
        if observed_time_in_ms_value is not None:
            try:
                observed_time_ms = int(observed_time_in_ms_value)
            except (ValueError, TypeError):
                # Handle conversion errors
                observed_time_ms = None     
        return AnalyzedControllerStatisticsValues(
            averageReadOpSize=data.get('averageReadOpSize'),
            averageWriteOpSize=data.get('averageWriteOpSize'),
            cacheHitBytesPercent=data.get('cacheHitBytesPercent'),
            combinedHitResponseTime=data.get('combinedHitResponseTime'),
            combinedHitResponseTimeStdDev=data.get('combinedHitResponseTimeStdDev'),
            combinedIOps=data.get('combinedIOps'),
            combinedResponseTime=data.get('combinedResponseTime'),
            combinedResponseTimeStdDev=data.get('combinedResponseTimeStdDev'),
            combinedThroughput=data.get('combinedThroughput'),
            controllerId=data.get('controllerId'),
            cpuAvgUtilization=data.get('cpuAvgUtilization'),
            # cpuAvgUtilizationPerCore=data.get('cpuAvgUtilizationPerCore'),
            # cpuAvgUtilizationPerCoreStdDev=data.get('cpuAvgUtilizationPerCoreStdDev'),
            ddpBytesPercent=data.get('ddpBytesPercent'),
            fullStripeWritesBytesPercent=data.get('fullStripeWritesBytesPercent'),
            maxCpuUtilization=data.get('maxCpuUtilization'),
            # maxCpuUtilizationPerCore=data.get('maxCpuUtilizationPerCore'),
            maxPossibleBpsUnderCurrentLoad=data.get('maxPossibleBpsUnderCurrentLoad'),
            maxPossibleIopsUnderCurrentLoad=data.get('maxPossibleIopsUnderCurrentLoad'),
            mirrorBytesPercent=data.get('mirrorBytesPercent'),
            observedTime=data.get('observedTime'),
            observedTimeInMS=str(observed_time_ms) if observed_time_ms is not None else None,
            otherIOps=data.get('otherIOps'),
            raid0BytesPercent=data.get('raid0BytesPercent'),
            raid1BytesPercent=data.get('raid1BytesPercent'),
            raid5BytesPercent=data.get('raid5BytesPercent'),
            raid6BytesPercent=data.get('raid6BytesPercent'),
            randomIosPercent=data.get('randomIosPercent'),
            readHitResponseTime=data.get('readHitResponseTime'),
            readHitResponseTimeStdDev=data.get('readHitResponseTimeStdDev'),
            readIOps=data.get('readIOps'),
            readOps=data.get('readOps'),
            readPhysicalIOps=data.get('readPhysicalIOps'),
            readResponseTime=data.get('readResponseTime'),
            readResponseTimeStdDev=data.get('readResponseTimeStdDev'),
            readThroughput=data.get('readThroughput'),
            sourceController=data.get('sourceController'),
            writeHitResponseTime=data.get('writeHitResponseTime'),
            writeHitResponseTimeStdDev=data.get('writeHitResponseTimeStdDev'),
            writeIOps=data.get('writeIOps'),
            writeOps=data.get('writeOps'),
            writePhysicalIOps=data.get('writePhysicalIOps'),
            writeResponseTime=data.get('writeResponseTime'),
            writeResponseTimeStdDev=data.get('writeResponseTimeStdDev'),
            writeThroughput=data.get('writeThroughput'),
            # Enriched fields
            controller_id=data.get('controller_id'),
            controller_label=data.get('controller_label'),
            controller_active=data.get('controller_active'),
            controller_model=data.get('controller_model'),
            interface_type=data.get('interface_type'),
            is_management_interface=data.get('is_management_interface'),
            system_name=data.get('system_name'),
            system_wwn=data.get('system_wwn'),
            system_id=data.get('system_id'),
            system_model=data.get('system_model'),
            system_firmware_version=data.get('system_firmware_version'),
            link_state=data.get('link_state'),
            current_speed=data.get('current_speed'),
            link_width=data.get('link_width'),
            port_state=data.get('port_state'),
            channel=data.get('channel'),
            storageSystemName=data.get('storageSystemName') or data.get('storage_system_name'),
            storageSystemWWN=data.get('storageSystemWWN') or data.get('storage_system_wwn'),
            _raw_data=data.copy()
        )

@dataclass
class AnalyzedControllerStatistics(BaseModel):
    """Configuration data for analyzedcontrollerstatistics"""
    statistics: Optional[List[AnalyzedControllerStatisticsValues]] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'AnalyzedControllerStatistics':
        return AnalyzedControllerStatistics(
            statistics=[
                AnalyzedControllerStatisticsValues.from_dict(item)
                for item in data.get('statistics', [])
            ],
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class HostGroupsConfig(BaseModel):
    """Configuration data for hostgroupsconfig"""
    clusterRef: Optional[str] = None
    confirmLUNMappingCreation: Optional[bool] = None
    id: Optional[str] = None
    isLun0Restricted: Optional[bool] = None
    isSAControlled: Optional[bool] = None
    label: Optional[str] = None
    name: Optional[str] = None
    protectionInformationCapableAccessMethod: Optional[bool] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'HostGroupsConfig':
        return HostGroupsConfig(
            clusterRef=data.get('clusterRef', 'unknown'),
            confirmLUNMappingCreation=data.get('confirmLUNMappingCreation'),
            id=data.get('id', 'unknown'),
            isLun0Restricted=data.get('isLun0Restricted'),
            isSAControlled=data.get('isSAControlled'),
            label=data.get('label'),
            name=data.get('name'),
            protectionInformationCapableAccessMethod=data.get('protectionInformationCapableAccessMethod'),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class HostConfigHostSidePorts:
    """Configuration data for hostconfig hostsideports"""
    id: Optional[str] = None
    type: Optional[str] = None
    address: Optional[str] = None
    label: Optional[str] = None
    mtpIoInterfaceType: Optional[str] = None
    name: Optional[str] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'HostConfigHostSidePorts':
        return HostConfigHostSidePorts(
            id=data.get('id', 'unknown'),
            type=data.get('type'),
            address=data.get('address'),
            label=data.get('label'),
            mtpIoInterfaceType=data.get('mtpIoInterfaceType'),
            name=data.get('name'),            
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class HostConfigHostInitiatorsNodeNames:
    """Configuration data for hostconfig Host Initiators Node Names"""
    ioInterfaceType: Optional[str] = None
    iscsiNodeName: Optional[str] = None
    remoteNodeWWN: Optional[str] = None
    nvmeNodeName: Optional[str] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'HostConfigHostInitiatorsNodeNames':
        return HostConfigHostInitiatorsNodeNames(
            ioInterfaceType=data.get('ioInterfaceType'),
            iscsiNodeName=data.get('iscsiNodeName'),
            remoteNodeWWN=data.get('remoteNodeWWN'),
            nvmeNodeName=data.get('nvmeNodeName'),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class HostConfigHostInitiators:
    """Configuration data for hostconfig Host Initiators"""
    initiatorRef: Optional[str] = None
    nodeName: Optional[HostConfigHostInitiatorsNodeNames] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'HostConfigHostInitiators':
        return HostConfigHostInitiators(
            initiatorRef=data.get('initiatorRef', 'unknown'),
            nodeName=HostConfigHostInitiatorsNodeNames.from_api_response(data.get('nodeName', {})),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class HostConfig(BaseModel):
    """Configuration data for hostconfig"""
    clusterRef: Optional[str] = None
    confirmLUNMappingCreation: Optional[bool] = None
    hostRef: Optional[str] = None
    hostSidePorts: Optional[List[HostConfigHostSidePorts]] = None
    hostTypeIndex: Optional[int] = None
    id: Optional[str] = None
    initiators: Optional[List[Dict]] = None
    isLargeBlockFormatHost: Optional[bool] = None
    isLun0Restricted: Optional[bool] = None
    isSAControlled: Optional[bool] = None
    label: Optional[str] = None
    name: Optional[str] = None
    ports: Optional[List[Any]] = None
    protectionInformationCapableAccessMethod: Optional[bool] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'HostConfig':
        return HostConfig(
            clusterRef=data.get('clusterRef'),
            confirmLUNMappingCreation=data.get('confirmLUNMappingCreation'),
            hostRef=data.get('hostRef'),
            hostSidePorts=[HostConfigHostSidePorts.from_api_response(port) for port in data.get('hostSidePorts', [])],
            hostTypeIndex=safe_int(data.get('hostTypeIndex')),
            id=data.get('id', 'unknown'),
            initiators=data.get('initiators', []),
            isLargeBlockFormatHost=data.get('isLargeBlockFormatHost'),
            isLun0Restricted=data.get('isLun0Restricted'),
            isSAControlled=data.get('isSAControlled'),
            label=data.get('label'),
            name=data.get('name'),
            ports=data.get('ports', []),
            protectionInformationCapableAccessMethod=data.get('protectionInformationCapableAccessMethod'),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class VolumeConsistencyGroupMembersConfig:
    """Configuration data for volumeconsistencygroupmembersconfig"""
    autoDeleteLimit: Optional[int] = None
    autoDeleteSnapshots: Optional[bool] = None
    baseVolumeName: Optional[str] = None                    # tag base_volume_name
    clusterSize: Optional[int] = None
    consistencyGroupId: Optional[str] = None                # tag consistency_group_id
    fullWarnThreshold: Optional[int] = None
    pitGroupId: Optional[str] = None                        # tag pit_group_id    
    repositoryVolume: Optional[str] = None
    totalRepositoryCapacity: Optional[int] = None
    totalRepositoryVolumes: Optional[int] = None
    totalSnapshotImages: Optional[int] = None
    totalSnapshotVolumes: Optional[int] = None
    usedRepositoryCapacity: Optional[str] = None
    volumeId: Optional[str] = None                          # tag volume_id
    volumeWwn: Optional[str] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'VolumeConsistencyGroupMembersConfig':
        return VolumeConsistencyGroupMembersConfig(
            autoDeleteLimit=safe_int(data.get('autoDeleteLimit')),
            autoDeleteSnapshots=data.get('autoDeleteSnapshots'),
            baseVolumeName=data.get('baseVolumeName'),
            clusterSize=safe_int(data.get('clusterSize')),
            consistencyGroupId=data.get('consistencyGroupId', 'unknown'),
            fullWarnThreshold=safe_int(data.get('fullWarnThreshold')),
            pitGroupId=data.get('pitGroupId', 'unknown'),
            repositoryVolume=data.get('repositoryVolume'),
            totalRepositoryCapacity=safe_int(data.get('totalRepositoryCapacity')),
            totalRepositoryVolumes=safe_int(data.get('totalRepositoryVolumes')),
            totalSnapshotImages=safe_int(data.get('totalSnapshotImages')),
            totalSnapshotVolumes=safe_int(data.get('totalSnapshotVolumes')),
            usedRepositoryCapacity=data.get('usedRepositoryCapacity'),
            volumeId=data.get('volumeId', 'unknown'),
            volumeWwn=data.get('volumeWwn'),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class SnapshotImages:
    """Configuration data for snapshotimages"""
    activeCOW: Optional[bool] = None
    baseVol: Optional[str] = None                       # tag base_vol
    consistencyGroupId: Optional[str] = None            # tag consistency_group_id
    creationMethod: Optional[str] = None
    id: Optional[str] = None
    isRollbackSource: Optional[bool] = None
    pitCapacity: Optional[int] = None
    pitGroupRef: Optional[str] = None
    pitRef: Optional[str] = None
    pitSequenceNumber: Optional[int] = None
    pitTimestamp: Optional[int] = None                  # snapshot date in seconds since epoch
    repositoryCapacityUtilization: Optional[int] = None
    status: Optional[str] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'SnapshotImages':
        return SnapshotImages(
            activeCOW=data.get('activeCOW'),
            baseVol=data.get('baseVol', 'unknown'),
            consistencyGroupId=data.get('consistencyGroupId', 'unknown'),
            creationMethod=data.get('creationMethod'),
            id=data.get('id', 'unknown'),
            isRollbackSource=data.get('isRollbackSource'),
            pitCapacity=safe_int(data.get('pitCapacity')),
            pitGroupRef=data.get('pitGroupRef', 'unknown'),
            pitRef=data.get('pitRef', 'unknown'),
            pitSequenceNumber=safe_int(data.get('pitSequenceNumber')),
            pitTimestamp=safe_int(data.get('pitTimestamp')),
            repositoryCapacityUtilization=safe_int(data.get('repositoryCapacityUtilization')),
            status=data.get('status'),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)



@dataclass
class SnapshotSchedule:
    """Configuration data for Snapshot Schedule"""
    action: Optional[str] = None
    creationTime: Optional[str] = None                          # schedule creation time in seconds since epoch
    id: Optional[str] = None
    lastRunTime: Optional[str] = None                           # last schedule run time in seconds since epoch         
    nextRunTime: Optional[str] = None                           # next schedule run time in seconds since epoch
    schedRef: Optional[str] = None
    schedule: Optional[Dict] = None
    scheduleStatus: Optional[str] = None
    stopTime: Optional[str] = None                              # schedule stop time in seconds since epoch or 0 to never stop
    targetObject: Optional[str] = None                          # tag: snapshot_target (volume or consistency group)
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'SnapshotSchedule':
        return SnapshotSchedule(
            action=data.get('action'),
            creationTime=data.get('creationTime'),
            id=data.get('id', 'unknown'),
            lastRunTime=data.get('lastRunTime'),
            nextRunTime=data.get('nextRunTime'),
            schedRef=data.get('schedRef', 'unknown'),
            schedule=data.get('schedule', {}),
            scheduleStatus=data.get('scheduleStatus'),
            stopTime=data.get('stopTime'),
            targetObject=data.get('targetObject', 'unknown'),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class SnapshotVolumesMembership:
    """Configuration data for snapshotvolumes membership"""
    viewType: Optional[str] = None
    cgViewRef: Optional[str] = None                     # tag cg_view_ref
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'SnapshotVolumesMembership':
        return SnapshotVolumesMembership(
            viewType=data.get('viewType'),
            cgViewRef=data.get('cgViewRef', 'unknown'),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class SnapshotVolumes:
    """Configuration data for snapshotvolumes"""
    accessMode: Optional[str] = None
    asyncMirrorSource: Optional[bool] = None
    asyncMirrorTarget: Optional[bool] = None
    basePIT: Optional[str] = None                        # tag base_pit
    baseVol: Optional[str] = None                        # tag base_vol
    baseVolumeCapacity: Optional[int] = None
    boundToPIT: Optional[bool] = None
    cloneCopy: Optional[bool] = None
    clusterSize: Optional[int] = None
    consistencyGroupId: Optional[str] = None             # tag consistency_group_id
    currentControllerId: Optional[str] = None
    currentManager: Optional[str] = None
    extendedUniqueIdentifier: Optional[str] = None
    fullWarnThreshold: Optional[int] = None
    id: Optional[str] = None                            # tag snapshot_volume_id 
    label: Optional[str] = None                         
    listOfMappings: Optional[List[Any]] = None
    mapped: Optional[bool] = None
    maxRepositoryCapacity: Optional[int] = None
    membership: Optional[SnapshotVolumesMembership] = None
    mgmtClientAttribute: Optional[int] = None
    name: Optional[str] = None                          # tag snapshot_volume_name  
    objectType: Optional[str] = None
    offline: Optional[bool] = None
    onlineVolumeCopy: Optional[bool] = None
    perms: Optional[Dict] = None
    pitBaseVolume: Optional[bool] = None
    preferredControllerId: Optional[str] = None
    preferredManager: Optional[str] = None
    protectionType: Optional[str] = None
    remoteMirrorSource: Optional[bool] = None
    remoteMirrorTarget: Optional[bool] = None
    repositoryCapacity: Optional[int] = None
    repositoryVolume: Optional[str] = None              # tag repository_volume_id
    status: Optional[str] = None                        # tag snapshot_volume_status
    totalSizeInBytes: Optional[int] = None
    unusableRepositoryCapacity: Optional[int] = None
    viewRef: Optional[str] = None
    viewSequenceNumber: Optional[int] = None
    viewTime: Optional[int] = None                      # snapshot time in seconds since epoch
    volumeCopySource: Optional[bool] = None
    volumeCopyTarget: Optional[bool] = None
    volumeFull: Optional[bool] = None
    volumeHandle: Optional[int] = None
    worldWideName: Optional[str] = None
    wwn: Optional[str] = None                          # tag snapshot_volume_wwn

    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'SnapshotVolumes':
        return SnapshotVolumes(
            accessMode=data.get('accessMode'),
            asyncMirrorSource=data.get('asyncMirrorSource'),
            asyncMirrorTarget=data.get('asyncMirrorTarget'),
            basePIT=data.get('basePIT', 'unknown'),
            baseVol=data.get('baseVol', 'unknown'),
            baseVolumeCapacity=safe_int(data.get('baseVolumeCapacity')),
            boundToPIT=data.get('boundToPIT'),
            cloneCopy=data.get('cloneCopy'),
            clusterSize=safe_int(data.get('clusterSize')),
            consistencyGroupId=data.get('consistencyGroupId', 'unknown'),
            currentControllerId=data.get('currentControllerId'),
            currentManager=data.get('currentManager'),
            extendedUniqueIdentifier=data.get('extendedUniqueIdentifier'),
            fullWarnThreshold=safe_int(data.get('fullWarnThreshold')),
            id=data.get('id', 'unknown'),
            label=data.get('label'),
            listOfMappings=data.get('listOfMappings', []),
            mapped=data.get('mapped'),
            maxRepositoryCapacity=safe_int(data.get('maxRepositoryCapacity')),
            membership=SnapshotVolumesMembership.from_api_response(data.get('membership', {})),
            mgmtClientAttribute=safe_int(data.get('mgmtClientAttribute')),
            name=data.get('name', 'unknown'),
            objectType=data.get('objectType'),
            offline=data.get('offline'),
            onlineVolumeCopy=data.get('onlineVolumeCopy'),
            perms=data.get('perms', {}),
            pitBaseVolume=data.get('pitBaseVolume'),
            preferredControllerId=data.get('preferredControllerId'),
            preferredManager=data.get('preferredManager'),
            protectionType=data.get('protectionType'),
            remoteMirrorSource=data.get('remoteMirrorSource'),
            remoteMirrorTarget=data.get('remoteMirrorTarget'),
            repositoryCapacity=safe_int(data.get('repositoryCapacity')),
            repositoryVolume=data.get('repositoryVolume', 'unknown'),
            status=data.get('status', 'unknown'),
            totalSizeInBytes=safe_int(data.get('totalSizeInBytes')),
            unusableRepositoryCapacity=safe_int(data.get('unusableRepositoryCapacity')),
            viewRef=data.get('viewRef'),
            viewSequenceNumber=safe_int(data.get('viewSequenceNumber')),
            viewTime=safe_int(data.get('viewTime')),
            volumeCopySource=data.get('volumeCopySource'),
            volumeCopyTarget=data.get('volumeCopyTarget'),
            volumeFull=data.get('volumeFull'),
            volumeHandle=safe_int(data.get('volumeHandle')),
            worldWideName=data.get('worldWideName'),
            wwn=data.get('wwn', 'unknown'),            
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class SnapshotGroups:
    """Configuration data for Snapshot Groups"""
    action: Optional[str] = None
    autoDeleteLimit: Optional[int] = None
    baseVolume: Optional[str] = None             # tag base_volume_name
    clusterSize: Optional[int] = None
    consistencyGroup: Optional[bool] = None      # tag is_consistency_group
    consistencyGroupRef: Optional[str] = None    # tag consistency_group_id
    creationPendingStatus: Optional[str] = None
    fullWarnThreshold: Optional[int] = None
    id: Optional[str] = None                     # tag snapshot_group_id
    label: Optional[str] = None
    maxBaseCapacity: Optional[int] = None
    maxRepositoryCapacity: Optional[int] = None
    name: Optional[str] = None                   # tag snapshot_group_name
    pitGroupRef: Optional[str] = None 
    repFullPolicy: Optional[str] = None
    repositoryCapacity: Optional[int] = None
    repositoryVolume: Optional[str] = None
    rollbackPriority: Optional[str] = None
    rollbackStatus: Optional[str] = None
    snapshotCount: Optional[int] = None
    status: Optional[str] = None
    unusableRepositoryCapacity: Optional[int] = None
    volcopyId: Optional[str] = None
    volumeHandle: Optional[int] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'SnapshotGroups':
        return SnapshotGroups(
            action=data.get('action'),
            autoDeleteLimit=safe_int(data.get('autoDeleteLimit')),
            baseVolume=data.get('baseVolume', 'unknown'),
            clusterSize=safe_int(data.get('clusterSize')),
            consistencyGroup=data.get('consistencyGroup'),
            consistencyGroupRef=data.get('consistencyGroupRef', 'unknown'),
            creationPendingStatus=data.get('creationPendingStatus'),
            fullWarnThreshold=safe_int(data.get('fullWarnThreshold')),
            id=data.get('id', 'unknown'),
            label=data.get('label'),
            maxBaseCapacity=safe_int(data.get('maxBaseCapacity')),
            maxRepositoryCapacity=safe_int(data.get('maxRepositoryCapacity')),
            name=data.get('name', 'unknown'),
            pitGroupRef=data.get('pitGroupRef', 'unknown'),
            repFullPolicy=data.get('repFullPolicy'),
            repositoryCapacity=safe_int(data.get('repositoryCapacity')),
            repositoryVolume=data.get('repositoryVolume'),
            rollbackPriority=data.get('rollbackPriority'),
            rollbackStatus=data.get('rollbackStatus'),
            snapshotCount=safe_int(data.get('snapshotCount')),
            status=data.get('status', 'unknown'),
            unusableRepositoryCapacity=safe_int(data.get('unusableRepositoryCapacity')),
            volcopyId=data.get('volcopyId'),
            volumeHandle=safe_int(data.get('volumeHandle')),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class ConsistencyGroupMembers:
    """Configuration data for consistencygroupmembers"""
    autoDeleteLimit: Optional[int] = None
    autoDeleteSnapshots: Optional[bool] = None
    baseVolumeName: Optional[str] = None            # tag base_volume_name
    clusterSize: Optional[int] = None
    consistencyGroupId: Optional[str] = None        # tag consistency_group_id
    fullWarnThreshold: Optional[int] = None
    pitGroupId: Optional[str] = None
    repositoryVolume: Optional[str] = None          # tag repository_volume_id
    totalRepositoryCapacity: Optional[int] = None
    totalRepositoryVolumes: Optional[int] = None
    totalSnapshotImages: Optional[int] = None
    totalSnapshotVolumes: Optional[int] = None
    usedRepositoryCapacity: Optional[int] = None
    volumeId: Optional[str] = None                 # tag volume_id
    volumeWwn: Optional[str] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'ConsistencyGroupMembers':
        return ConsistencyGroupMembers(
            autoDeleteLimit=safe_int(data.get('autoDeleteLimit')),
            autoDeleteSnapshots=data.get('autoDeleteSnapshots'),
            baseVolumeName=data.get('baseVolumeName'),
            clusterSize=safe_int(data.get('clusterSize')),
            consistencyGroupId=data.get('consistencyGroupId', 'unknown'),
            fullWarnThreshold=safe_int(data.get('fullWarnThreshold')),
            pitGroupId=data.get('pitGroupId', 'unknown'),
            repositoryVolume=data.get('repositoryVolume', 'unknown'),
            totalRepositoryCapacity=safe_int(data.get('totalRepositoryCapacity')),
            totalRepositoryVolumes=safe_int(data.get('totalRepositoryVolumes')),
            totalSnapshotImages=safe_int(data.get('totalSnapshotImages')),
            totalSnapshotVolumes=safe_int(data.get('totalSnapshotVolumes')),
            usedRepositoryCapacity=safe_int(data.get('usedRepositoryCapacity')),
            volumeId=data.get('volumeId', 'unknown'),
            volumeWwn=data.get('volumeWwn'),            
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class StoragePoolsActionProgress:
    """Configuration data for Storage Pools Action Progress
    curl -X GET "https://api:8443/devmgr/v2/storage-systems/600A098000F63714000000005E79C17C/storage-pools/04000000600A098000E3C1B000002CED62CF874D/action-progress"
    It gives lists of dicts like [[{}],[]], but lists can be empty so [[],[]]  is possible for no actions running 
    """
    volumeRef: Optional[str] = None                           # tag volume_id
    currentAction: Optional[str] = None                       # current action description, e.g. 'rebalancing'
    progressPercentage: Optional[int] = None                  # percentage 0-100
    estimatedTimeToCompletion: Optional[int] = None           # in seconds
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'StoragePoolsActionProgress':
        return StoragePoolsActionProgress(
            volumeRef=data.get('volumeRef', 'unknown'),
            currentAction=data.get('currentAction'),
            progressPercentage=safe_int(data.get('progressPercentage')),
            estimatedTimeToCompletion=safe_int(data.get('estimatedTimeToCompletion')),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)
    
@dataclass
class VolumeExpandProgress:
    """Configuration data for Volume Expand Action Progress
    curl -X GET "https://api:8443/devmgr/v2/storage-systems/1/volumes/02000000600A098000E3C1B0000034D8689951AF/expand"
    """
    percentComplete: Optional[int] = None          # percentage 0-100
    timeToCompletion: Optional[int] = None         # in seconds
    action: Optional[str] = None                   # current action description, e.g. 'expanding'
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'VolumeExpandProgress':
        return VolumeExpandProgress(
            percentComplete=safe_int(data.get('percentComplete')),
            timeToCompletion=safe_int(data.get('timeToCompletion')),
            action=data.get('action'),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)

@dataclass
class SystemFailures:
    """Configuration data for System Failures
    https://api:8443/devmgr/v2/storage-systems/{system}/failures
    """
    failureType: Optional[str] = None             # tag: failure_type; eg. 'hostRedundancyLost'
    objectRef: Optional[str] = None
    objectType: Optional[str] = None              # tag: object_type, eg. 'host', 'powerSupply'
    objectData: Optional[str] = None
    extraData: Optional[str] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_api_response(data: Dict) -> 'SystemFailures':
        return SystemFailures(
            failureType=data.get('failureType', 'unknown'),
            objectRef=data.get('objectRef'),
            objectType=data.get('objectType', 'unknown'),
            objectData=data.get('objectData'),
            extraData=data.get('extraData'),
            _raw_data=data.copy()
        )

    def get_raw(self, key, default=None):
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)