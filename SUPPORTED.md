# Поддерживаемые модели

Матрица ниже описывает layout, который использует `switchLIVE` при walk-test.
Если фактический `show ports` / `show interfaces status` на стенде отличается,
править нужно vendor profile, а не core flow.

## D-Link

### Часто встречаются
- DES-1228: 24xFE RJ45 + 2xGE RJ45 + 2xGE RJ45/SFP combo.
- DES-3200-10: 8xFE RJ45 + 2xGE RJ45/SFP combo.
- DGS-3000-10: 8xGE RJ45 + 2xGE RJ45/SFP combo.
- DGS-1210-28/ME: 24xGE RJ45 + 4xGE SFP.
- DGS-1210-28/SX: 24xGE RJ45 + 4xGE SFP.
- DGS-3100-24/TC: 20xGE RJ45 + 4xGE RJ45/SFP combo.
- DGS-3120-24/SC: 16xGE SFP + 8xGE RJ45/SFP combo.
- DGS-3612: 12xGE RJ45 + 4xGE RJ45/SFP combo.
- DGS-3620/SC: 20xGE SFP + 4xGE RJ45/SFP combo + 4x10G SFP+.
- DGS-3630/SC: 20xGE SFP + 4xGE RJ45/SFP combo + 4x10G SFP+.
- DGS-3420/SC: 20xGE SFP + 4xGE RJ45/SFP combo + 2x10G SFP+.
- DGS-3627: 24xGE RJ45 + 4xGE RJ45/SFP combo.

### Редкие гости
- DES-3200: профиль DES-3200-10.
- DES-3200-C1: профиль DES-3200-10.
- DES-3028: 24xFE RJ45 + 2xGE RJ45 + 2xGE RJ45/SFP combo.
- DES-3526: 24xFE RJ45 + 2xGE RJ45/SFP combo.

## Eltex

### MES23xx
- MES2324B: 24xGE RJ45 + 4x10G SFP+.
- MES2324FB: 20xGE SFP + 4xGE RJ45/SFP combo + 4x10G SFP+.

## CLI команды

### D-Link

- paging off: `disable clipaging`
- identity: `show switch`
- ports: `show ports`
- MAC table: `show fdb`
- counters: `show ports {port} counters`
- shutdown/no shutdown: `config ports {port} state disable|enable`
- SFP/DOM probe: `show transceiver`, если команда доступна в прошивке.

### Eltex MES2324

- paging off: `terminal datadump`
- identity: `show version`
- ports: `show interfaces status`
- MAC table: `show mac address-table`
- counters: `show interface counters {port}`
- SFP/DOM probe: `show fiber-ports optical-transceiver interface {port}`
- shutdown/no shutdown: `configure terminal`, `interface {port}`, `shutdown|no shutdown`

## Проверенные источники

- D-Link DES-3028 CLI/spec: https://ftp.dlink.ru/pub/Switch/DES-3028-3052/Description/DES-3028_28P_52_52P_CLI_v1.00.pdf
- D-Link DES-3200-10: https://www.dlink.ru/mn/products/1/1719.html
- D-Link DGS-3000-10TC datasheet: https://legacyfiles.us.dlink.com/DGS-3000-10TC/REVB/DGS-3000-10TC_REVB_DATASHEET.pdf
- D-Link DGS-3100-24: https://www.dlink.ru/en/products/1/721.html
- D-Link DGS-3120-24SC datasheet: https://www.dlink.com/gr/el/-/media/business_products/dgs/dgs-3120/datasheet/dgs_3120_series_b1_datasheet_en_eu.pdf
- D-Link DGS-3420-26SC: https://www.dlink.ru/mn/products/1/1467.html
- D-Link DGS-3620-28SC: https://support.dlink.com/resource/products/DGS-3620-SERIES/REVB/DGS-3620_SERIES_REVB_HARDWARE_INSTALL_GUIDE_v2.61_WW_EN.pdf
- D-Link DGS-3630-28SC: https://www.dlink.com/en/products/dgs-3630-28sc-28-port-layer-3-stackable-managed-gigabit-fiber-switch
- D-Link DGS-3612/DGS-3627 family: https://ftp.dlink.ru/pub/Switch/DGS-3627G/Description/DGS-3600_Series_FW_R2.8_HW_Installation_Guide_%28for_WW%29.pdf
- D-Link DGS-1210-28/ME: https://www.dlink.com/en/products/dgs-1210-28-me-28-port-gigabit-metro-ethernet-switch
- Eltex MES23xx datasheet/manual: https://simaxcom.net/wp-content/uploads/2019/12/MES23xx_datasheet_4.0.10.1_en.pdf
