"""
Knowledge Base Manager for Restaurant Information.
Loads and provides access to restaurant configuration, menu, and about us content.
"""

import json
import os
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
import pytz


# ============================================================================
# Pydantic Models for Knowledge Base Data
# ============================================================================

class OperatingHours(BaseModel):
    """Operating hours for a single day."""
    open: str
    close: str
    is_closed: bool


class Address(BaseModel):
    """Restaurant address information."""
    street: str
    city: str
    postal_code: str
    country: str
    full_address: str
    google_maps_url: str


class Contact(BaseModel):
    """Restaurant contact information."""
    phone: str
    email: str
    website: str


class ReservationSettings(BaseModel):
    """Reservation configuration settings."""
    min_guests: int
    max_guests: int
    default_time_slot_hours: float
    advance_booking_hours: int
    max_advance_booking_days: int
    large_party_threshold: int
    large_party_note: str


class MenuItem(BaseModel):
    """A single menu item."""
    name: str
    description: str
    price: float
    tags: List[str] = []


class MenuCategory(BaseModel):
    """A category of menu items."""
    name: str
    description: str
    items: List[MenuItem]


class RestaurantInfo(BaseModel):
    """Summary of restaurant information for the agent."""
    name: str
    tagline: str
    description: str
    full_address: str
    phone: str
    email: str
    website: str
    operating_hours_summary: str
    is_currently_open: bool
    current_day_hours: str
    reservation_rules: str


# ============================================================================
# Knowledge Base Manager
# ============================================================================

class KnowledgeBaseManager:
    """
    Manager class for loading and accessing restaurant knowledge base.
    Implements singleton pattern to ensure single instance.
    """
    _instance = None
    _config: Dict[str, Any] = None
    _about_us: Dict[str, Any] = None
    _menu: Dict[str, Any] = None
    _knowledgebase_path: str = None

    @classmethod
    def get_instance(cls, knowledgebase_path: str = None):
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls(knowledgebase_path)
        return cls._instance

    def __init__(self, knowledgebase_path: str = None):
        """Initialize the knowledge base manager."""
        if knowledgebase_path is None:
            # Default path relative to this file
            self._knowledgebase_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'knowledgebase'
            )
        else:
            self._knowledgebase_path = knowledgebase_path
        
        self._load_all()

    def _load_json_file(self, filename: str) -> Dict[str, Any]:
        """Load a JSON file from the knowledgebase directory."""
        filepath = os.path.join(self._knowledgebase_path, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: Knowledge base file not found: {filepath}")
            return {}
        except json.JSONDecodeError as e:
            print(f"Warning: Error parsing JSON file {filepath}: {e}")
            return {}

    def _load_all(self):
        """Load all knowledge base files."""
        self._config = self._load_json_file('restaurant_config.json')
        self._about_us = self._load_json_file('about_us.json')
        self._menu = self._load_json_file('menu.json')

    def reload(self):
        """Reload all knowledge base files (useful for updates)."""
        self._load_all()

    # ========================================================================
    # Restaurant Configuration Accessors
    # ========================================================================

    def get_restaurant_name(self) -> str:
        """Get the restaurant name."""
        return self._config.get('restaurant', {}).get('name', 'Our Restaurant')

    def get_restaurant_tagline(self) -> str:
        """Get the restaurant tagline."""
        return self._config.get('restaurant', {}).get('tagline', '')

    def get_restaurant_description(self) -> str:
        """Get the restaurant description."""
        return self._config.get('restaurant', {}).get('description', '')

    def get_contact_info(self) -> Contact:
        """Get contact information."""
        contact_data = self._config.get('contact', {})
        return Contact(
            phone=contact_data.get('phone', ''),
            email=contact_data.get('email', ''),
            website=contact_data.get('website', '')
        )

    def get_address(self) -> Address:
        """Get address information."""
        address_data = self._config.get('address', {})
        return Address(
            street=address_data.get('street', ''),
            city=address_data.get('city', ''),
            postal_code=address_data.get('postal_code', ''),
            country=address_data.get('country', ''),
            full_address=address_data.get('full_address', ''),
            google_maps_url=address_data.get('google_maps_url', '')
        )

    def get_operating_hours(self, day: str = None) -> Dict[str, OperatingHours]:
        """Get operating hours for all days or a specific day."""
        hours_data = self._config.get('operating_hours', {})
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        
        if day and day.lower() in days:
            day_data = hours_data.get(day.lower(), {})
            return {
                day.lower(): OperatingHours(
                    open=day_data.get('open', ''),
                    close=day_data.get('close', ''),
                    is_closed=day_data.get('is_closed', False)
                )
            }
        
        result = {}
        for d in days:
            day_data = hours_data.get(d, {})
            result[d] = OperatingHours(
                open=day_data.get('open', ''),
                close=day_data.get('close', ''),
                is_closed=day_data.get('is_closed', False)
            )
        return result

    def get_operating_hours_formatted(self) -> str:
        """Get a formatted string of all operating hours."""
        hours = self.get_operating_hours()
        lines = []
        for day, info in hours.items():
            if info.is_closed:
                lines.append(f"{day.capitalize()}: Closed")
            else:
                lines.append(f"{day.capitalize()}: {info.open} - {info.close}")
        
        special_notes = self._config.get('operating_hours', {}).get('special_notes', '')
        if special_notes:
            lines.append(f"\nNote: {special_notes}")
        
        return '\n'.join(lines)

    def is_restaurant_open(self) -> tuple[bool, str]:
        """
        Check if the restaurant is currently open.
        Returns (is_open, message).
        """
        tz = pytz.timezone(self._config.get('operating_hours', {}).get('timezone', 'Europe/Zagreb'))
        now = datetime.now(tz)
        day_name = now.strftime('%A').lower()
        
        hours = self.get_operating_hours(day_name)
        day_hours = hours.get(day_name)
        
        if not day_hours or day_hours.is_closed:
            return False, f"We are closed on {day_name.capitalize()}s."
        
        current_time = now.strftime('%H:%M')
        
        # Handle closing time after midnight
        close_time = day_hours.close
        if close_time == '00:00':
            close_time = '24:00'
        
        if day_hours.open <= current_time < close_time:
            return True, f"We are currently open until {day_hours.close}."
        elif current_time < day_hours.open:
            return False, f"We open today at {day_hours.open}."
        else:
            return False, f"We are closed for today. We were open until {day_hours.close}."

    def get_reservation_settings(self) -> ReservationSettings:
        """Get reservation settings."""
        settings = self._config.get('reservation_settings', {})
        return ReservationSettings(
            min_guests=settings.get('min_guests', 1),
            max_guests=settings.get('max_guests', 20),
            default_time_slot_hours=settings.get('default_time_slot_hours', 2),
            advance_booking_hours=settings.get('advance_booking_hours', 1),
            max_advance_booking_days=settings.get('max_advance_booking_days', 60),
            large_party_threshold=settings.get('large_party_threshold', 8),
            large_party_note=settings.get('large_party_note', '')
        )

    def get_urls(self) -> Dict[str, str]:
        """Get configured URLs."""
        return self._config.get('urls', {})

    # ========================================================================
    # About Us Accessors
    # ========================================================================

    def get_about_us(self) -> Dict[str, Any]:
        """Get the full about us content."""
        return self._about_us

    def get_about_us_story(self) -> str:
        """Get the about us story as formatted text."""
        story = self._about_us.get('story', {})
        paragraphs = story.get('paragraphs', [])
        return '\n\n'.join(paragraphs)

    def get_chef_info(self) -> Dict[str, str]:
        """Get chef information."""
        return self._about_us.get('chef', {})

    def get_restaurant_values(self) -> List[Dict[str, str]]:
        """Get restaurant values."""
        return self._about_us.get('values', [])

    # ========================================================================
    # Menu Accessors
    # ========================================================================

    def get_menu(self) -> Dict[str, Any]:
        """Get the full menu."""
        return self._menu

    def get_menu_categories(self) -> List[MenuCategory]:
        """Get all menu categories with items."""
        categories = []
        for cat_data in self._menu.get('categories', []):
            items = [
                MenuItem(
                    name=item.get('name', ''),
                    description=item.get('description', ''),
                    price=item.get('price', 0),
                    tags=item.get('tags', [])
                )
                for item in cat_data.get('items', [])
            ]
            categories.append(MenuCategory(
                name=cat_data.get('name', ''),
                description=cat_data.get('description', ''),
                items=items
            ))
        return categories

    def get_menu_formatted(self) -> str:
        """Get a formatted text version of the menu."""
        lines = []
        currency = self._menu.get('currency', 'EUR')
        
        for category in self.get_menu_categories():
            lines.append(f"\n=== {category.name.upper()} ===")
            lines.append(f"{category.description}\n")
            
            for item in category.items:
                tags_str = ''
                if item.tags:
                    tag_symbols = []
                    if 'vegetarian' in item.tags:
                        tag_symbols.append('(V)')
                    if 'vegan' in item.tags:
                        tag_symbols.append('(VG)')
                    if 'gluten_free' in item.tags:
                        tag_symbols.append('(GF)')
                    tags_str = ' ' + ' '.join(tag_symbols)
                
                lines.append(f"• {item.name}{tags_str} - {currency} {item.price:.2f}")
                lines.append(f"  {item.description}")
        
        # Add tasting menu if available
        tasting = self._menu.get('tasting_menu', {})
        if tasting.get('available'):
            lines.append(f"\n=== CHEF'S TASTING MENU ===")
            lines.append(f"{tasting.get('description', '')}")
            lines.append(f"Price: {currency} {tasting.get('price', 0):.2f}")
            lines.append(f"Wine pairing: +{currency} {tasting.get('wine_pairing_price', 0):.2f}")
        
        return '\n'.join(lines)

    def search_menu(self, query: str) -> List[MenuItem]:
        """Search menu items by name or description."""
        query_lower = query.lower()
        results = []
        
        for category in self.get_menu_categories():
            for item in category.items:
                if query_lower in item.name.lower() or query_lower in item.description.lower():
                    results.append(item)
        
        return results

    # ========================================================================
    # Combined Restaurant Info for Agent
    # ========================================================================

    def get_restaurant_info_for_agent(self) -> RestaurantInfo:
        """Get a summary of restaurant information for the agent to use."""
        is_open, hours_message = self.is_restaurant_open()
        
        tz = pytz.timezone(self._config.get('operating_hours', {}).get('timezone', 'Europe/Zagreb'))
        now = datetime.now(tz)
        day_name = now.strftime('%A').lower()
        hours = self.get_operating_hours(day_name)
        day_hours = hours.get(day_name)
        
        current_day_hours = "Closed" if day_hours.is_closed else f"{day_hours.open} - {day_hours.close}"
        
        settings = self.get_reservation_settings()
        reservation_rules = (
            f"Guests: {settings.min_guests}-{settings.max_guests}. "
            f"Default time slot: {settings.default_time_slot_hours} hours. "
            f"Book at least {settings.advance_booking_hours} hour(s) in advance. "
            f"{settings.large_party_note}"
        )
        
        contact = self.get_contact_info()
        address = self.get_address()
        
        return RestaurantInfo(
            name=self.get_restaurant_name(),
            tagline=self.get_restaurant_tagline(),
            description=self.get_restaurant_description(),
            full_address=address.full_address,
            phone=contact.phone,
            email=contact.email,
            website=contact.website,
            operating_hours_summary=self.get_operating_hours_formatted(),
            is_currently_open=is_open,
            current_day_hours=current_day_hours,
            reservation_rules=reservation_rules
        )


# ============================================================================
# Module-level convenience functions
# ============================================================================

def get_kb() -> KnowledgeBaseManager:
    """Get the knowledge base manager instance."""
    return KnowledgeBaseManager.get_instance()


# ============================================================================
# Test
# ============================================================================

if __name__ == "__main__":
    kb = KnowledgeBaseManager.get_instance()
    
    print("=== Restaurant Info ===")
    info = kb.get_restaurant_info_for_agent()
    print(f"Name: {info.name}")
    print(f"Address: {info.full_address}")
    print(f"Phone: {info.phone}")
    print(f"Currently Open: {info.is_currently_open}")
    print(f"Today's Hours: {info.current_day_hours}")
    
    print("\n=== Operating Hours ===")
    print(kb.get_operating_hours_formatted())
    
    print("\n=== Menu Preview ===")
    categories = kb.get_menu_categories()
    for cat in categories[:2]:  # First 2 categories
        print(f"\n{cat.name}:")
        for item in cat.items[:2]:  # First 2 items
            print(f"  - {item.name}: EUR {item.price}")
