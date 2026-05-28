import React, { useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ActivityIndicator,
  Alert, ScrollView, Image, TextInput, Switch,
} from 'react-native';
import { launchImageLibrary, launchCamera } from 'react-native-image-picker';
import { api } from '../api/client';
import { COLORS } from '../theme';

type Stage = 'idle' | 'scanning' | 'review' | 'saving';

type Item = {
  name: string;
  receipt_name?: string;
  quantity: string;
  unit_price: string;
  total_price: string;
  vat_applicable: boolean;
  category?: string;
};

function blankItem(): Item {
  return { name: '', quantity: '1', unit_price: '', total_price: '', vat_applicable: true };
}

function resultToItems(raw: any[]): Item[] {
  return (raw || []).map(i => ({
    name: i.name || i.receipt_name || '',
    receipt_name: i.receipt_name,
    quantity: String(i.quantity ?? 1),
    unit_price: i.unit_price != null ? String(i.unit_price) : '',
    total_price: i.total_price != null ? String(i.total_price) : '',
    vat_applicable: i.vat_applicable !== false,
    category: i.category,
  }));
}

export default function ScanScreen() {
  const [stage, setStage] = useState<Stage>('idle');
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [error, setError] = useState('');

  const [store, setStore] = useState('');
  const [date, setDate] = useState('');
  const [total, setTotal] = useState('');
  const [currency, setCurrency] = useState('ZAR');
  const [items, setItems] = useState<Item[]>([]);

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
      setStore(data.store || '');
      setDate(data.date || '');
      setTotal(data.total != null ? String(data.total) : '');
      setCurrency(data.currency || 'ZAR');
      setItems(resultToItems(data.items));
      setStage('review');
    } catch (e: any) {
      setError(e.message || 'Scan failed');
      setStage('idle');
    }
  };

  const confirm = async () => {
    setStage('saving');
    try {
      const qty = (item: Item) => parseFloat(item.quantity) || 1;
      const up = (item: Item) => item.unit_price !== '' ? parseFloat(item.unit_price) : undefined;
      const tp = (item: Item) => {
        if (item.total_price !== '') return parseFloat(item.total_price);
        const u = up(item);
        return u != null ? u * qty(item) : undefined;
      };
      const payload = {
        store: store.trim() || null,
        date: date.trim() || null,
        total: total !== '' ? parseFloat(total) : null,
        currency: currency.trim() || 'ZAR',
        items: items.map(i => ({
          name: i.name || 'Unknown',
          receipt_name: i.receipt_name || i.name,
          category: i.category,
          quantity: qty(i),
          unit_type: 'unit',
          unit_price: up(i),
          total_price: tp(i),
          vat_applicable: i.vat_applicable,
        })),
      };
      await api.confirmReceipt(payload);
      reset();
      Alert.alert('Saved', 'Receipt saved to your history.');
    } catch (e: any) {
      setError(e.message || 'Save failed');
      setStage('review');
    }
  };

  const reset = () => {
    setStage('idle');
    setImageUri(null);
    setStore(''); setDate(''); setTotal(''); setCurrency('ZAR'); setItems([]);
    setError('');
  };

  const updateItem = (idx: number, patch: Partial<Item>) => {
    setItems(prev => prev.map((item, i) => i === idx ? { ...item, ...patch } : item));
  };

  if (stage === 'scanning') {
    return (
      <View style={[s.root, s.center]}>
        <ActivityIndicator size="large" color={COLORS.accent} />
        <Text style={s.scanningText}>Processing receipt…</Text>
        <Text style={s.scanningSubText}>AI is extracting items</Text>
      </View>
    );
  }

  if (stage === 'review' || stage === 'saving') {
    return (
      <ScrollView style={s.root} contentContainerStyle={s.reviewContent} keyboardShouldPersistTaps="handled">
        <View style={s.reviewHeader}>
          <Text style={s.reviewTitle}>Review Receipt</Text>
          <TouchableOpacity onPress={reset}><Text style={s.linkText}>Discard</Text></TouchableOpacity>
        </View>

        {imageUri && <Image source={{ uri: imageUri }} style={s.previewImg} resizeMode="contain" />}

        {/* Editable header */}
        <View style={s.metaCard}>
          <Text style={s.cardSectionLabel}>Receipt Details</Text>
          <Field label="Store" value={store} onChange={setStore} />
          <Field label="Date" value={date} onChange={setDate} placeholder="YYYY-MM-DD" />
          <View style={s.twoCol}>
            <View style={{ flex: 2, marginRight: 8 }}>
              <Field label="Total" value={total} onChange={setTotal} keyboardType="decimal-pad" placeholder="0.00" />
            </View>
            <View style={{ flex: 1 }}>
              <Field label="Currency" value={currency} onChange={setCurrency} autoCapitalize="characters" />
            </View>
          </View>
        </View>

        {/* Editable items */}
        <View style={s.itemsCard}>
          <View style={s.itemsCardHeader}>
            <Text style={s.cardSectionLabel}>Items ({items.length})</Text>
            <TouchableOpacity style={s.addBtn} onPress={() => setItems(prev => [...prev, blankItem()])}>
              <Text style={s.addBtnText}>+ Add</Text>
            </TouchableOpacity>
          </View>

          {items.map((item, idx) => (
            <View key={idx} style={s.itemEdit}>
              <View style={s.itemEditRow}>
                <TextInput
                  style={[s.itemInput, { flex: 1 }]}
                  value={item.name}
                  onChangeText={v => updateItem(idx, { name: v })}
                  placeholder="Item name"
                  placeholderTextColor={COLORS.textMuted}
                />
                <TouchableOpacity onPress={() => setItems(prev => prev.filter((_, i) => i !== idx))} style={s.delBtn}>
                  <Text style={s.delBtnText}>✕</Text>
                </TouchableOpacity>
              </View>
              <View style={s.itemEditRow}>
                <View style={s.miniField}>
                  <Text style={s.miniLabel}>Qty</Text>
                  <TextInput style={s.itemInput} value={item.quantity} onChangeText={v => updateItem(idx, { quantity: v })} keyboardType="decimal-pad" placeholderTextColor={COLORS.textMuted} />
                </View>
                <View style={s.miniField}>
                  <Text style={s.miniLabel}>Unit Price</Text>
                  <TextInput style={s.itemInput} value={item.unit_price} onChangeText={v => updateItem(idx, { unit_price: v })} keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor={COLORS.textMuted} />
                </View>
                <View style={s.miniField}>
                  <Text style={s.miniLabel}>Total</Text>
                  <TextInput style={s.itemInput} value={item.total_price} onChangeText={v => updateItem(idx, { total_price: v })} keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor={COLORS.textMuted} />
                </View>
              </View>
              <View style={s.vatRow}>
                <Text style={s.vatLabel}>VAT Applicable</Text>
                <Switch
                  value={item.vat_applicable}
                  onValueChange={v => updateItem(idx, { vat_applicable: v })}
                  trackColor={{ false: COLORS.surface2, true: COLORS.accent + '88' }}
                  thumbColor={item.vat_applicable ? COLORS.accent : COLORS.textMuted}
                />
              </View>
            </View>
          ))}
        </View>

        {error ? <Text style={s.error}>{error}</Text> : null}

        <TouchableOpacity style={[s.confirmBtn, stage === 'saving' && s.btnDisabled]} onPress={confirm} disabled={stage === 'saving'}>
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

function Field({ label, value, onChange, placeholder, keyboardType, autoCapitalize }: any) {
  return (
    <View style={s.field}>
      <Text style={s.fieldLabel}>{label}</Text>
      <TextInput
        style={s.fieldInput}
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor={COLORS.textMuted}
        keyboardType={keyboardType}
        autoCapitalize={autoCapitalize ?? 'words'}
        autoCorrect={false}
      />
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
  previewImg: { width: '100%', height: 180, borderRadius: 4, backgroundColor: COLORS.surface2, marginBottom: 14 },
  metaCard: { backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 14, marginBottom: 12 },
  cardSectionLabel: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 9, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 12 },
  field: { marginBottom: 10 },
  fieldLabel: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 9, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 },
  fieldInput: { backgroundColor: COLORS.surface2, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, color: COLORS.text, padding: 8, fontFamily: 'monospace', fontSize: 13 },
  twoCol: { flexDirection: 'row' },
  itemsCard: { backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 14, marginBottom: 20 },
  itemsCardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  addBtn: { borderWidth: 1, borderColor: COLORS.accent, borderRadius: 3, paddingHorizontal: 8, paddingVertical: 4 },
  addBtnText: { color: COLORS.accent, fontFamily: 'monospace', fontSize: 10 },
  itemEdit: { borderBottomWidth: 1, borderBottomColor: COLORS.border, paddingVertical: 8, gap: 6 },
  itemEditRow: { flexDirection: 'row', gap: 6, alignItems: 'center' },
  itemInput: { backgroundColor: COLORS.surface2, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, color: COLORS.text, padding: 7, fontFamily: 'monospace', fontSize: 12 },
  delBtn: { paddingHorizontal: 8, paddingVertical: 6 },
  delBtnText: { color: COLORS.red, fontSize: 16 },
  miniField: { flex: 1 },
  miniLabel: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 8, textTransform: 'uppercase', marginBottom: 3 },
  vatRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  vatLabel: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 10 },
  confirmBtn: { backgroundColor: COLORS.accent, borderRadius: 4, padding: 16, alignItems: 'center' },
  btnDisabled: { opacity: 0.5 },
  confirmBtnText: { color: '#000', fontFamily: 'monospace', fontSize: 13, fontWeight: 'bold', letterSpacing: 1 },
});
