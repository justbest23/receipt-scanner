import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform, ActivityIndicator } from 'react-native';
import { api } from '../api/client';
import { useAuth } from '../AuthContext';
import { COLORS } from '../theme';

export default function LoginScreen() {
  const { setUser } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const login = async () => {
    if (!username || !password) { setError('Enter username and password'); return; }
    setLoading(true); setError('');
    try {
      const user = await api.login(username, password);
      setUser(user);
    } catch (e: any) {
      setError(e.message || 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView style={s.root} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={s.card}>
        <View style={s.logoRow}>
          <View style={s.logoMark}><Text style={s.logoIcon}>⬡</Text></View>
          <Text style={s.logoText}>BASKET</Text>
        </View>
        <Text style={s.sub}>Receipt Scanner</Text>

        <TextInput
          style={s.input}
          placeholder="Username or email"
          placeholderTextColor={COLORS.textMuted}
          value={username}
          onChangeText={setUsername}
          autoCapitalize="none"
          autoCorrect={false}
          returnKeyType="next"
        />
        <TextInput
          style={s.input}
          placeholder="Password"
          placeholderTextColor={COLORS.textMuted}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          returnKeyType="go"
          onSubmitEditing={login}
        />

        {error ? <Text style={s.error}>{error}</Text> : null}

        <TouchableOpacity style={[s.btn, loading && s.btnDisabled]} onPress={login} disabled={loading}>
          {loading ? <ActivityIndicator color="#000" /> : <Text style={s.btnText}>SIGN IN</Text>}
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLORS.bg, alignItems: 'center', justifyContent: 'center', padding: 24 },
  card: { width: '100%', maxWidth: 360, backgroundColor: COLORS.surface, borderRadius: 6, padding: 32, borderWidth: 1, borderColor: COLORS.border },
  logoRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 6 },
  logoMark: { width: 32, height: 32, borderWidth: 1.5, borderColor: COLORS.accent, alignItems: 'center', justifyContent: 'center' },
  logoIcon: { color: COLORS.accent, fontSize: 16 },
  logoText: { color: COLORS.text, fontFamily: 'monospace', fontSize: 14, letterSpacing: 2 },
  sub: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 10, letterSpacing: 1, marginBottom: 28, textTransform: 'uppercase' },
  input: { backgroundColor: COLORS.surface2, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 4, color: COLORS.text, padding: 12, marginBottom: 12, fontFamily: 'monospace', fontSize: 13 },
  error: { color: COLORS.red, fontFamily: 'monospace', fontSize: 11, marginBottom: 12 },
  btn: { backgroundColor: COLORS.accent, borderRadius: 4, padding: 14, alignItems: 'center' },
  btnDisabled: { opacity: 0.5 },
  btnText: { color: '#000', fontFamily: 'monospace', fontSize: 12, fontWeight: 'bold', letterSpacing: 1 },
});
