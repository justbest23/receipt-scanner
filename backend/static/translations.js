/* translations.js — shared i18n for all pages */
const SUPPORTED_LANGUAGES = [
  { code: 'en', name: 'English',  flag: '🇬🇧' },
  { code: 'sv', name: 'Svenska',  flag: '🇸🇪' },
];

const TRANSLATIONS = {
  en: {
    // nav
    nav_scan:      'Scan',
    nav_history:   'History',
    nav_analytics: 'Analytics',
    nav_settings:  'Settings',
    nav_logout:    'Log out',
    // scan page
    page_scan:          'Scan a Receipt',
    lbl_store:          'Store',
    lbl_date:           'Date',
    lbl_total:          'Total',
    lbl_currency:       'Currency',
    lbl_language:       'Language',
    lbl_items:          'Line Items',
    lbl_category:       'Category',
    lbl_quantity:       'Quantity',
    lbl_unit:           'Unit',
    lbl_unit_price:     'Unit Price',
    lbl_total_price:    'Total Price',
    lbl_vat:            'VAT',
    btn_scan:           'Scan',
    btn_save:           'Save Receipt',
    btn_discard:        'Discard',
    btn_add_item:       '+ Add item',
    btn_uploading:      'Uploading…',
    // history
    page_history:       'History',
    lbl_search:         'Search',
    lbl_filter:         'Filter by category',
    lbl_no_receipts:    'No receipts yet',
    // analytics
    page_analytics:     'Analytics',
    lbl_period:         'Period',
    lbl_spending:       'Spending',
    // settings
    page_settings:      'Settings',
    sec_account:        'Account',
    lbl_display_name:   'Display Name',
    lbl_username:       'Username',
    lbl_email:          'Email',
    lbl_new_password:   'New Password',
    lbl_confirm_pw:     'Confirm Password',
    lbl_leave_blank:    '(leave blank to keep)',
    btn_save_changes:   'Save Changes',
    sec_corrections:    'Ingredient Names',
    // categories
    cat_fruit:          'Fruit',
    cat_vegetable:      'Vegetable',
    cat_dairy:          'Dairy',
    cat_meat:           'Meat',
    cat_seafood:        'Seafood',
    cat_bakery:         'Bakery',
    cat_pantry:         'Pantry',
    cat_frozen:         'Frozen',
    cat_beverages:      'Beverages',
    cat_snacks:         'Snacks',
    cat_alcohol:        'Alcohol',
    cat_household:      'Household',
    cat_toiletries:     'Toiletries',
    cat_clothing:       'Clothing',
    cat_footwear:       'Footwear',
    cat_accessories:    'Accessories',
    cat_beauty:         'Beauty',
    cat_homeware:       'Homeware',
    cat_sport:          'Sport',
    cat_fuel:           'Fuel',
    cat_discount:       'Discount',
    cat_other:          'Other',
  },
  sv: {
    // nav
    nav_scan:      'Skanna',
    nav_history:   'Historik',
    nav_analytics: 'Analys',
    nav_settings:  'Inställningar',
    nav_logout:    'Logga ut',
    // scan page
    page_scan:          'Skanna ett kvitto',
    lbl_store:          'Butik',
    lbl_date:           'Datum',
    lbl_total:          'Totalt',
    lbl_currency:       'Valuta',
    lbl_language:       'Språk',
    lbl_items:          'Artiklar',
    lbl_category:       'Kategori',
    lbl_quantity:       'Antal',
    lbl_unit:           'Enhet',
    lbl_unit_price:     'Styckpris',
    lbl_total_price:    'Totalpris',
    lbl_vat:            'Moms',
    btn_scan:           'Skanna',
    btn_save:           'Spara kvitto',
    btn_discard:        'Kassera',
    btn_add_item:       '+ Lägg till artikel',
    btn_uploading:      'Laddar upp…',
    // history
    page_history:       'Historik',
    lbl_search:         'Sök',
    lbl_filter:         'Filtrera efter kategori',
    lbl_no_receipts:    'Inga kvitton ännu',
    // analytics
    page_analytics:     'Analys',
    lbl_period:         'Period',
    lbl_spending:       'Utgifter',
    // settings
    page_settings:      'Inställningar',
    sec_account:        'Konto',
    lbl_display_name:   'Visningsnamn',
    lbl_username:       'Användarnamn',
    lbl_email:          'E-post',
    lbl_new_password:   'Nytt lösenord',
    lbl_confirm_pw:     'Bekräfta lösenord',
    lbl_leave_blank:    '(lämna tomt för att behålla)',
    btn_save_changes:   'Spara ändringar',
    sec_corrections:    'Ingrediensnamn',
    // categories
    cat_fruit:          'Frukt',
    cat_vegetable:      'Grönsak',
    cat_dairy:          'Mejeri',
    cat_meat:           'Kött',
    cat_seafood:        'Fisk & Skaldjur',
    cat_bakery:         'Bageri',
    cat_pantry:         'Skafferi',
    cat_frozen:         'Fryst',
    cat_beverages:      'Drycker',
    cat_snacks:         'Snacks',
    cat_alcohol:        'Alkohol',
    cat_household:      'Hushåll',
    cat_toiletries:     'Toalettartiklar',
    cat_clothing:       'Kläder',
    cat_footwear:       'Skor',
    cat_accessories:    'Tillbehör',
    cat_beauty:         'Skönhet',
    cat_homeware:       'Husgeråd',
    cat_sport:          'Sport',
    cat_fuel:           'Bränsle',
    cat_discount:       'Rabatt',
    cat_other:          'Övrigt',
  },
};

/* ── Public API ─────────────────────────────────────────────────────────────── */

let _currentLang = 'en';

function t(key) {
  return (TRANSLATIONS[_currentLang] || {})[key]
      || (TRANSLATIONS['en']          || {})[key]
      || key;
}

function applyTranslations() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.getAttribute('data-i18n'));
  });
  document.querySelectorAll('[data-i18n-ph]').forEach(el => {
    el.placeholder = t(el.getAttribute('data-i18n-ph'));
  });
  document.documentElement.lang = _currentLang;
}

function initLang(lang) {
  _currentLang = (lang || 'en').toLowerCase().split('-')[0];
  if (!TRANSLATIONS[_currentLang]) _currentLang = 'en';
  applyTranslations();
}

function getLang() { return _currentLang; }
