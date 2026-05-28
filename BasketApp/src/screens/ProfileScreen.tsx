import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ScrollView, Alert, ActivityIndicator, Modal, FlatList,
} from 'react-native';
import { useAuth } from '../AuthContext';
import { api } from '../api/client';
import { COLORS } from '../theme';

const CURRENCIES = [
  'ZAR', 'USD', 'EUR', 'GBP', 'AUD', 'CAD', 'NZD', 'CHF', 'JPY', 'CNY',
  'INR', 'BRL', 'MXN', 'SEK', 'NOK', 'DKK', 'SGD', 'HKD', 'KES', 'NGN',
  'GHS', 'EGP', 'MAD', 'TZS', 'UGX', 'ZMW', 'BWP', 'NAD',
];

export default function ProfileScreen() {
  const { user, setUser, logout } = useAuth();
  const [displayName, setDisplayName] = useState(user?.display_name ?? '');
  const [username, setUsername] = useState(user?.username ?? '');
  const [email, setEmail] = useState(user?.email ?? '');
  const [currency, setCurrency] = useState(user?.currency ?? 'ZAR');
  const [pw1, setPw1] = useState('');
  const [pw2, setPw2] = useState('');
  const [saving, setSaving] = useState(false);
  const [currencyModal, setCurrencyModal] = useState(false);
  const [currencySearch, setCurrencySearch] = useState('');

  const save = async () => {
    if (pw1 && pw1 !== pw2) { Alert.alert('Error', 'Passwords do not match'); return; }
    setSaving(true);
    try {
      const body: any = { display_name: displayName, username, email, currency };
      if (pw1) body.password = pw1;
      const updated = await api.updateProfile(body);
      setUser(updated);
      setPw1(''); setPw2('');
      Alert.alert('Saved', 'Profile updated.');
    } catch (e: any) {
      Alert.alert('Error', e.message || 'Save failed');
    } finally { setSaving(false); }
  };

  const filteredCurrencies = CURRENCIES.filter(c =>
    c.toLowerCase().includes(currencySearch.toLowerCase())
  );

  return (
    <ScrollView style={s.root} contentContainerStyle={s.content}>
      <Text style={s.title}>Profile</Text>

      <View style={s.card}>
        <Field label="Display Name" value={displayName} onChange={setDisplayName} />
        <Field label="Username" value={username} onChange={setUsername} autoCapitalize="none" />
        <Field label="Email" value={email} onChange={setEmail} keyboardType="email-address" autoCapitalize="none" />

        <View style={s.fieldWrap}>
          <Text style={s.fieldLabel}>Currency</Text>
          <TouchableOpacity style={s.currencyBtn} onPress={() => setCurrencyModal(true)}>
            <Text style={s.currencyValue}>{currency}</Text>
            <Text style={s.currencyArrow}>▼</Text>
          </TouchableOpacity>
        </View>

        <View style={s.divider}><Text style={s.dividerText}>Change Password</Text></View>

        <Field label="New Password" value={pw1} onChange={setPw1} secure placeholder="Leave blank to keep" />
        <Field label="Confirm Password" value={pw2} onChange={setPw2} secure placeholder="Repeat new password" />

        <TouchableOpacity style={[s.saveBtn, saving && s.saveBtnDisabled]} onPress={save} disabled={saving}>
          {saving ? <ActivityIndicator color="#000" /> : <Text style={s.saveBtnText}>SAVE CHANGES</Text>}
        </TouchableOpacity>
      </View>

      <TouchableOpacity style={s.logoutBtn} onPress={() => Alert.alert('Logout', 'Are you sure?', [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Logout', style: 'destructive', onPress: logout },
      ])}>
        <Text style={s.logoutText}>LOGOUT</Text>
      </TouchableOpacity>

      <Modal visible={currencyModal} transparent animationType="slide">
        <View style={s.overlay}>
          <View style={s.sheet}>
            <Text style={s.sheetTitle}>Select Currency</Text>
            <TextInput
              style={s.searchInput}
              value={currencySearch}
              onChangeText={setCurrencySearch}
              placeholder="Search…"
              placeholderTextColor={COLORS.textMuted}
              autoCapitalize="characters"
            />
            <FlatList
              data={filteredCurrencies}
              keyExtractor={c => c}
              style={{ maxHeight: 300 }}
              renderItem={({ item }) => (
                <TouchableOpacity
                  style={[s.currencyItem, item === currency && s.currencyItemActive]}
                  onPress={() => { setCurrency(item); setCurrencyModal(false); setCurrencySearch(''); }}>
                  <Text style={[s.currencyItemText, item === currency && s.currencyItemTextActive]}>{item}</Text>
                </TouchableOpacity>
              )}
            />
            <TouchableOpacity style={s.cancelBtn} onPress={() => { setCurrencyModal(false); setCurrencySearch(''); }}>
              <Text style={s.cancelText}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
}

function Field({ label, value, onChange, secure, placeholder, autoCapitalize, keyboardType }: any) {
  return (
    <View style={s.field}>
      <Text style={s.fieldLabel}>{label}</Text>
      <TextInput
        style={s.input}
        value={value}
        onChangeText={onChange}
        secureTextEntry={secure}
        placeholder={placeholder}
        placeholderTextColor={COLORS.textMuted}
        autoCapitalize={autoCapitalize ?? 'words'}
        keyboardType={keyboardType}
        autoCorrect={false}
      />
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLORS.bg },
  content: { padding: 16, paddingBottom: 40 },
  title: { color: COLORS.text, fontFamily: 'monospace', fontSize: 16, letterSpacing: 1, textTransform: 'uppercase', marginBottom: 16 },
  card: { backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 16, marginBottom: 14 },
  field: { marginBottom: 12 },
  fieldWrap: { marginBottom: 12 },
  fieldLabel: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 9, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 5 },
  input: { backgroundColor: COLORS.surface2, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, color: COLORS.text, padding: 10, fontFamily: 'monospace', fontSize: 13 },
  currencyBtn: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: COLORS.surface2, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, padding: 10 },
  currencyValue: { color: COLORS.text, fontFamily: 'monospace', fontSize: 13 },
  currencyArrow: { color: COLORS.textMuted, fontSize: 10 },
  divider: { borderTopWidth: 1, borderTopColor: COLORS.border, paddingTop: 12, marginBottom: 12, marginTop: 4 },
  dividerText: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 9, textTransform: 'uppercase', letterSpacing: 0.5 },
  saveBtn: { backgroundColor: COLORS.accent, borderRadius: 3, padding: 13, alignItems: 'center', marginTop: 4 },
  saveBtnDisabled: { opacity: 0.5 },
  saveBtnText: { color: '#000', fontFamily: 'monospace', fontSize: 11, fontWeight: 'bold', letterSpacing: 0.5 },
  logoutBtn: { borderWidth: 1, borderColor: COLORS.red, borderRadius: 4, padding: 14, alignItems: 'center' },
  logoutText: { color: COLORS.red, fontFamily: 'monospace', fontSize: 12, letterSpacing: 1 },
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: COLORS.surface, borderTopLeftRadius: 12, borderTopRightRadius: 12, padding: 20, paddingBottom: 36 },
  sheetTitle: { color: COLORS.text, fontFamily: 'monospace', fontSize: 14, letterSpacing: 1, textTransform: 'uppercase', marginBottom: 12 },
  searchInput: { backgroundColor: COLORS.surface2, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, color: COLORS.text, padding: 10, fontFamily: 'monospace', fontSize: 13, marginBottom: 10 },
  currencyItem: { paddingVertical: 12, paddingHorizontal: 8, borderBottomWidth: 1, borderBottomColor: COLORS.border },
  currencyItemActive: { backgroundColor: COLORS.accent + '22' },
  currencyItemText: { color: COLORS.text, fontFamily: 'monospace', fontSize: 13 },
  currencyItemTextActive: { color: COLORS.accent, fontWeight: 'bold' },
  cancelBtn: { marginTop: 10, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, padding: 13, alignItems: 'center' },
  cancelText: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 11 },
});
