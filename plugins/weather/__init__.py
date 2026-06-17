# -*- coding: utf-8 -*-
"""
天气显示插件

从公开 API 获取天气信息并显示。
支持 IP 自动定位城市，也支持手动选择。
"""

import logging
import urllib.request
import urllib.parse
from features.plugin_system.base import PluginBase

logger = logging.getLogger(__name__)

# 常见中国城市列表（供手动选择）
CITY_OPTIONS = [
    '自动定位', '北京', '上海', '广州', '深圳', '杭州', '成都', '武汉',
    '南京', '重庆', '西安', '天津', '苏州', '长沙', '郑州', '青岛',
    '大连', '厦门', '宁波', '东莞', '佛山', '合肥', '昆明', '哈尔滨',
    '济南', '福州', '温州', '石家庄', '太原', '沈阳', '贵阳', '南昌',
]


class WeatherPlugin(PluginBase):
    """天气显示插件"""

    name = '天气显示'
    version = '1.1.0'
    author = 'StickyNote'
    description = '显示当前城市天气信息（支持自动定位）'

    def on_load(self):
        self._city = self.config.get('city', '自动定位')
        self._resolved_city = None  # 缓存自动定位结果
        self.register_tray_menu_item('🌤 查看天气', self.show_weather)
        self.register_context_menu('🌤 查看天气', self._show_weather_for_note)

    def get_config_fields(self):
        return [
            {
                'key': 'city',
                'label': '城市',
                'type': 'select',
                'default': '自动定位',
                'options': CITY_OPTIONS,
                'help': '选择"自动定位"将使用 IP 地址检测所在城市',
            },
        ]

    def on_config_changed(self, key, value):
        if key == 'city':
            self._city = value
            self._resolved_city = None  # 清除缓存，下次重新定位

    def _auto_locate_city(self):
        """通过 IP 地址自动定位城市"""
        if self._resolved_city:
            return self._resolved_city
        try:
            # 使用 ip-api.com 免费接口（无需 API Key）
            req = urllib.request.Request(
                'http://ip-api.com/json/?lang=zh-CN&fields=city',
                headers={'User-Agent': 'StickyNote/1.0'}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                import json
                data = json.loads(resp.read().decode('utf-8'))
                city = data.get('city', '')
                if city:
                    self._resolved_city = city
                    logger.info(f'IP 自动定位城市: {city}')
                    return city
        except Exception as e:
            logger.warning(f'IP 自动定位失败: {e}，使用默认城市')
        # 回退到默认
        self._resolved_city = '北京'
        return '北京'

    def _get_effective_city(self):
        """获取实际使用的城市名"""
        if self._city == '自动定位':
            return self._auto_locate_city()
        return self._city

    def show_weather(self):
        """获取并显示天气"""
        city = self._get_effective_city()
        try:
            city_encoded = urllib.parse.quote(city)
            url = f'https://wttr.in/{city_encoded}?format=%l:+%c+%t+%h+%w&lang=zh'
            req = urllib.request.Request(url, headers={'User-Agent': 'StickyNote/1.0'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                weather_text = resp.read().decode('utf-8').strip()
            display_city = f'{city}' + (' (自动定位)' if self._city == '自动定位' else '')
            self.show_notification('🌤 天气', f'{display_city}: {weather_text}')
        except Exception as e:
            logger.error(f'获取天气失败: {e}')
            self.show_notification('🌤 天气', f'获取 {city} 天气失败: {e}')

    def _show_weather_for_note(self, note_id=None):
        """右键菜单触发的天气显示"""
        self.show_weather()
