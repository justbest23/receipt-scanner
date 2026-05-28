import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView, Alert, ActivityIndicator } from 'react-native';
import { useAuth } from '../AuthContext';
import { api } from '../api/client';
import { COLORS } from '../theme';

export default function ProfileScreen() {
  const { user, setUser, logout } = useAuth();
  const [displayName, setDisplayName] = useState(user?.display_name ?? '');
  const [username, setUsername] = useState(user?.username ?? '');
  const [email, setEmail] = useState(user?.email ?? '');
  const [pw1, setPw1] = useState('');
  const [pw2, setPw2] = useState('');
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (pw1 && pw1 !== pw2) { Alert.alert('Error', 'Passwords do not match'); return; }
    setSaving(true);
    try {
      const body: any = { display_name: displayName, username, email };
      if (pw1) body.password = pw1;
      const updated = await api.updateProfile(body);
      setUser(updated);
      setPw1(''); setPw2('');
      Alert.alert('Saved', 'Profile updated.');
    } catch (e: any) {
      Alert.alert('Error', e.message || 'Save failed');
    } finally { setSaving(false); }
  };

  return (
    <ScrollView style={s.root} contentContainerStyle={s.content}>
      <Text style={s.title}>Profile</Text>

      <View style={s.card}>
        <Field label="Display Name" value={displayName} onChange={setDisplayName} />
        <Field label="Username" value={username} onChange={setUsername} autoCapitalize="none" />
        <Field label="Email" value={email} onChange={setEmail} keyboardType="email-address" autoCapitalize="none" />

        <View style={s.divider}><Text style={s.dividerText}>Change Password</Text></View>

        <Field label="New Password" value={pw1} onChange={setPw1} secure placeholder="Leave blank to keep" />
        <Field label="Confirm Password" value={pw2} onChange={setPw2} secure placeholder="Repeat new password" />

        <TouchableOpacity style={[s.saveBtn, saving && s.saveBtnDisabled]} onPress={save} disabled={saving}>
          {saving ? <ActivityIndicator color="#000" /> : <Text style={s.saveBtnText}>SAVE CHANGES</Text>}
        </TouchableOpacity>
      </View>

      <View style={s.card}>
        <Text style={s.sectionLabel}>Android App</Text>
        <Text style={s.hint}>Download the native APK to install on your device.</Text>
        <TouchableOpacity style={s.downloadBtn} onPress={() => Alert.alert('Download', 'Visit basket.trog.co.za/download/basket.apk in your browser to download the APK.')}>
          <Text style={s.downloadBtnText}>⬇  Download APK</Text>
        </TouchableOpacity>
      </View>

      <TouchableOpacity style={s.logoutBtn} onPress={() => Alert.alert('Logout', 'Are you sure?', [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Logout', style: 'destructive', onPress: logout },
      ])}>
        <Text style={s.logoutText}>LOGOUT</Text>
      </TouchableOpacity>
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
  fieldLabel: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 9, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 5 },
  input: { backgroundColor: COLORS.surface2, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, color: COLORS.text, padding: 10, fontFamily: 'monospace', fontSize: 13 },
  divider: { borderTopWidth: 1, borderTopColor: COLORS.border, paddingTop: 12, marginBottom: 12, marginTop: 4 },
  dividerText: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 9, textTransform: 'uppercase', letterSpacing: 0.5 },
  saveBtn: { backgroundColor: COLORS.accent, borderRadius: 3, padding: 13, alignItems: 'center', marginTop: 4 },
  saveBtnDisabled: { opacity: 0.5 },
  saveBtnText: { color: '#000', fontFamily: 'monospace', fontSize: 11, fontWeight: 'bold', letterSpacing: 0.5 },
  sectionLabel: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 },
  hint: { color: COLORS.textMuted, fontSize: 12, marginBottom: 10 },
  downloadBtn: { borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, padding: 10, alignItems: 'center' },
  downloadBtnText: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 11 },
  logoutBtn: { borderWidth: 1, borderColor: COLORS.red, borderRadius: 4, padding: 14, alignItems: 'center' },
  logoutText: { color: COLORS.red, fontFamily: 'monospace', fontSize: 12, letterSpacing: 1 },
});
