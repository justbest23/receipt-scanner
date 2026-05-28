import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator, Alert, ScrollView, Image, TextInput } from 'react-native';
import { launchImageLibrary, launchCamera } from 'react-native-image-picker';
import { api } from '../api/client';
import { COLORS } from '../theme';

type Stage = 'idle' | 'scanning' | 'review' | 'saving';

export default function ScanScreen() {
  const [stage, setStage] = useState<Stage>('idle');
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');

  const pick = async (fromCamera: boolean) => {
    const fn = fromCamera ? launchCamera : launchImageLibrary;
    const res = await fn({ mediaType: 'photo', quality: 0.9 });
    if (res.didCancel || !res.assets?.[0]) return;
    const asset = res.assets[0];
    setImageUri(asset.uri!);
    setStage('scanning');
    setError('');
    try {
      const data = await api.scan(asset.uri!, asset.type ?? 'image/jpeg', asset.fileName ?? 'receipt.jpg');
      setResult(data);
      setStage('review');
    } catch (e: any) {
      setError(e.message || 'Scan failed');
      setStage('idle');
    }
  };

  const confirm = async () => {
    setStage('saving');
    try {
      await api.confirmReceipt(result);
      setStage('idle');
      setImageUri(null);
      setResult(null);
      Alert.alert('Saved', 'Receipt saved to your history.');
    } catch (e: any) {
      setError(e.message || 'Save failed');
      setStage('review');
    }
  };

  const reset = () => { setStage('idle'); setImageUri(null); setResult(null); setError(''); };

  if (stage === 'scanning') {
    return (
      <View style={[s.root, s.center]}>
        <ActivityIndicator size="large" color={COLORS.accent} />
        <Text style={s.scanningText}>Processing receipt…</Text>
        <Text style={s.scanningSubText}>AI is extracting items</Text>
      </View>
    );
  }

  if (stage === 'review' && result) {
    return (
      <ScrollView style={s.root} contentContainerStyle={s.reviewContent}>
        <View style={s.reviewHeader}>
          <Text style={s.reviewTitle}>Review Receipt</Text>
          <TouchableOpacity onPress={reset}><Text style={s.linkText}>Discard</Text></TouchableOpacity>
        </View>

        {imageUri && <Image source={{ uri: imageUri }} style={s.previewImg} resizeMode="contain" />}

        <View style={s.metaCard}>
          <Row label="Store" value={result.store || 'Unknown'} />
          <Row label="Date" value={result.date || '—'} />
          <Row label="Total" value={result.total != null ? `R ${result.total.toFixed(2)}` : '—'} accent />
        </View>

        {(result.items || []).length > 0 && (
          <View style={s.itemsCard}>
            <Text style={s.sectionLabel}>Items ({result.items.length})</Text>
            {result.items.map((item: any, i: number) => (
              <View key={i} style={s.itemRow}>
                <Text style={s.itemName} numberOfLines={2}>{item.name || item.receipt_name}</Text>
                <Text style={s.itemPrice}>R {(item.total_price ?? item.unit_price ?? 0).toFixed(2)}</Text>
              </View>
            ))}
          </View>
        )}

        {error ? <Text style={s.error}>{error}</Text> : null}

        <TouchableOpacity style={s.confirmBtn} onPress={confirm} disabled={stage === 'saving'}>
          {stage === 'saving'
            ? <ActivityIndicator color="#000" />
            : <Text style={s.confirmBtnText}>SAVE RECEIPT</Text>}
        </TouchableOpacity>
      </ScrollView>
    );
  }

  return (
    <View style={[s.root, s.center]}>
      <View style={s.logoRow}>
        <View style={s.logoMark}><Text style={s.logoIcon}>⬡</Text></View>
        <Text style={s.appTitle}>BASKET</Text>
      </View>
      <Text style={s.tagline}>Scan a receipt to get started</Text>

      {error ? <Text style={s.error}>{error}</Text> : null}

      <TouchableOpacity style={s.primaryBtn} onPress={() => pick(true)}>
        <Text style={s.primaryBtnText}>📷  Take Photo</Text>
      </TouchableOpacity>

      <TouchableOpacity style={s.secondaryBtn} onPress={() => pick(false)}>
        <Text style={s.secondaryBtnText}>🖼  Choose from Gallery</Text>
      </TouchableOpacity>
    </View>
  );
}

function Row({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <View style={s.metaRow}>
      <Text style={s.metaLabel}>{label}</Text>
      <Text style={[s.metaValue, accent && { color: COLORS.accent }]}>{value}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLORS.bg },
  center: { alignItems: 'center', justifyContent: 'center', padding: 32 },
  logoRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 },
  logoMark: { width: 36, height: 36, borderWidth: 1.5, borderColor: COLORS.accent, alignItems: 'center', justifyContent: 'center' },
  logoIcon: { color: COLORS.accent, fontSize: 18 },
  appTitle: { color: COLORS.text, fontFamily: 'monospace', fontSize: 18, letterSpacing: 3 },
  tagline: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 11, marginBottom: 48 },
  scanningText: { color: COLORS.text, fontFamily: 'monospace', fontSize: 14, marginTop: 20, letterSpacing: 1 },
  scanningSubText: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 11, marginTop: 6 },
  primaryBtn: { backgroundColor: COLORS.accent, borderRadius: 4, paddingVertical: 16, paddingHorizontal: 32, width: '100%', alignItems: 'center', marginBottom: 12 },
  primaryBtnText: { color: '#000', fontFamily: 'monospace', fontSize: 13, fontWeight: 'bold', letterSpacing: 1 },
  secondaryBtn: { backgroundColor: 'transparent', borderRadius: 4, paddingVertical: 14, paddingHorizontal: 32, width: '100%', alignItems: 'center', borderWidth: 1, borderColor: COLORS.border2 },
  secondaryBtnText: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 12, letterSpacing: 0.5 },
  error: { color: COLORS.red, fontFamily: 'monospace', fontSize: 11, marginBottom: 16, textAlign: 'center' },
  reviewContent: { padding: 16, paddingBottom: 40 },
  reviewHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 },
  reviewTitle: { color: COLORS.text, fontFamily: 'monospace', fontSize: 14, letterSpacing: 1, textTransform: 'uppercase' },
  linkText: { color: COLORS.accent, fontFamily: 'monospace', fontSize: 11 },
  previewImg: { width: '100%', height: 200, borderRadius: 4, backgroundColor: COLORS.surface2, marginBottom: 14 },
  metaCard: { backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 14, marginBottom: 12 },
  metaRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5 },
  metaLabel: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5 },
  metaValue: { color: COLORS.text, fontFamily: 'monospace', fontSize: 12 },
  itemsCard: { backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 14, marginBottom: 20 },
  sectionLabel: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 10 },
  itemRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: COLORS.border },
  itemName: { color: COLORS.text, fontSize: 13, flex: 1, marginRight: 8 },
  itemPrice: { color: COLORS.accent, fontFamily: 'monospace', fontSize: 12 },
  confirmBtn: { backgroundColor: COLORS.accent, borderRadius: 4, padding: 16, alignItems: 'center' },
  confirmBtnText: { color: '#000', fontFamily: 'monospace', fontSize: 13, fontWeight: 'bold', letterSpacing: 1 },
});
