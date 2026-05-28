import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, ActivityIndicator, TouchableOpacity,
  Alert, TextInput, Switch,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { api } from '../api/client';
import { COLORS } from '../theme';

type Item = {
  id?: number;
  name: string;
  receipt_name?: string;
  category?: string;
  quantity: string;
  unit_price: string;
  total_price: string;
  vat_applicable: boolean;
  unit_type?: string;
};

function blankItem(): Item {
  return { name: '', quantity: '1', unit_price: '', total_price: '', vat_applicable: true };
}

function itemFromApi(i: any): Item {
  return {
    id: i.id,
    name: i.name || i.receipt_name || '',
    receipt_name: i.receipt_name,
    category: i.category,
    quantity: String(i.quantity ?? 1),
    unit_price: i.unit_price != null ? String(i.unit_price) : '',
    total_price: i.total_price != null ? String(i.total_price) : '',
    vat_applicable: i.vat_applicable !== false,
    unit_type: i.unit_type,
  };
}

function itemToApi(i: Item) {
  const qty = parseFloat(i.quantity) || 1;
  const up = i.unit_price !== '' ? parseFloat(i.unit_price) : undefined;
  const tp = i.total_price !== '' ? parseFloat(i.total_price) : (up != null ? up * qty : undefined);
  return {
    id: i.id,
    name: i.name || 'Unknown',
    receipt_name: i.receipt_name || i.name,
    category: i.category,
    quantity: qty,
    unit_type: i.unit_type || 'unit',
    unit_price: up,
    total_price: tp,
    vat_applicable: i.vat_applicable,
  };
}

export default function ReceiptDetailScreen() {
  const nav = useNavigation<any>();
  const { params } = useRoute<any>();
  const [receipt, setReceipt] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);

  const [store, setStore] = useState('');
  const [date, setDate] = useState('');
  const [total, setTotal] = useState('');
  const [currency, setCurrency] = useState('');
  const [items, setItems] = useState<Item[]>([]);

  const load = useCallback(async () => {
    try {
      const r = await api.receipt(params.id);
      setReceipt(r);
      resetFromReceipt(r);
    } catch { Alert.alert('Error', 'Failed to load receipt'); }
    finally { setLoading(false); }
  }, [params.id]);

  useEffect(() => { load(); }, []);

  const resetFromReceipt = (r: any) => {
    setStore(r.store || '');
    setDate(r.date || '');
    setTotal(r.total != null ? String(r.total) : '');
    setCurrency(r.currency || 'ZAR');
    setItems((r.items || []).map(itemFromApi));
  };

  const cancelEdit = () => {
    resetFromReceipt(receipt);
    setEditing(false);
  };

  const save = async () => {
    setSaving(true);
    try {
      const updated = await api.updateReceipt(params.id, {
        store_name: store.trim() || null,
        receipt_date: date.trim() || null,
        total: total !== '' ? parseFloat(total) : null,
        currency: currency.trim() || null,
        items: items.map(itemToApi),
      });
      setReceipt(updated);
      resetFromReceipt(updated);
      setEditing(false);
    } catch (e: any) {
      Alert.alert('Error', e.message || 'Save failed');
    } finally { setSaving(false); }
  };

  const del = () => {
    Alert.alert('Delete Receipt', 'Are you sure? This cannot be undone.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: async () => {
        await api.deleteReceipt(params.id).catch(() => {});
        nav.goBack();
      }},
    ]);
  };

  const updateItem = (idx: number, patch: Partial<Item>) => {
    setItems(prev => prev.map((item, i) => i === idx ? { ...item, ...patch } : item));
  };

  const deleteItem = (idx: number) => {
    Alert.alert('Remove Item', 'Remove this line item?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Remove', style: 'destructive', onPress: () => setItems(prev => prev.filter((_, i) => i !== idx)) },
    ]);
  };

  if (loading) return <View style={s.center}><ActivityIndicator color={COLORS.accent} size="large" /></View>;
  if (!receipt) return <View style={s.center}><Text style={s.empty}>Receipt not found</Text></View>;

  const taxable = items.filter(i => i.vat_applicable).reduce((sum, i) => sum + (parseFloat(i.total_price) || 0), 0);
  const zeroRated = items.filter(i => !i.vat_applicable).reduce((sum, i) => sum + (parseFloat(i.total_price) || 0), 0);
  const cur = currency || 'R';

  return (
    <ScrollView style={s.root} contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">

      {/* Title row */}
      <View style={s.titleRow}>
        {editing
          ? <TextInput style={s.storeInput} value={store} onChangeText={setStore} placeholder="Store name" placeholderTextColor={COLORS.textMuted} />
          : <Text style={s.storeName} numberOfLines={1}>{receipt.store || 'Unknown Store'}</Text>
        }
        {!editing && (
          <TouchableOpacity onPress={() => setEditing(true)} style={s.editBtn}>
            <Text style={s.editBtnText}>Edit</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* Meta cells */}
      <View style={s.metaGrid}>
        <View style={s.metaCell}>
          <Text style={s.metaLabel}>Date</Text>
          {editing
            ? <TextInput style={s.metaInput} value={date} onChangeText={setDate} placeholder="YYYY-MM-DD" placeholderTextColor={COLORS.textMuted} />
            : <Text style={s.metaValue}>{receipt.date || '—'}</Text>}
        </View>
        <View style={s.metaCell}>
          <Text style={s.metaLabel}>Total</Text>
          {editing
            ? <TextInput style={s.metaInput} value={total} onChangeText={setTotal} keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor={COLORS.textMuted} />
            : <Text style={[s.metaValue, { color: COLORS.accent }]}>{cur} {(receipt.total ?? 0).toFixed(2)}</Text>}
        </View>
        <View style={s.metaCell}>
          <Text style={s.metaLabel}>Currency</Text>
          {editing
            ? <TextInput style={s.metaInput} value={currency} onChangeText={setCurrency} autoCapitalize="characters" placeholder="ZAR" placeholderTextColor={COLORS.textMuted} />
            : <Text style={s.metaValue}>{receipt.currency || 'ZAR'}</Text>}
        </View>
        <View style={s.metaCell}>
          <Text style={s.metaLabel}>Items</Text>
          <Text style={s.metaValue}>{items.length}</Text>
        </View>
      </View>

      {/* VAT breakdown */}
      {(taxable > 0 || zeroRated > 0) && (
        <View style={s.vatBox}>
          <Text style={s.sectionLabel}>VAT Breakdown</Text>
          {taxable > 0 && <VatRow label="Taxable (15%)" value={`${cur} ${taxable.toFixed(2)}`} />}
          {zeroRated > 0 && <VatRow label="Zero-rated" value={`${cur} ${zeroRated.toFixed(2)}`} />}
        </View>
      )}

      {/* Line items */}
      <View style={s.section}>
        <View style={s.sectionHeaderRow}>
          <Text style={s.sectionLabel}>Line Items ({items.length})</Text>
          {editing && (
            <TouchableOpacity style={s.addItemBtn} onPress={() => setItems(prev => [...prev, blankItem()])}>
              <Text style={s.addItemBtnText}>+ Add Item</Text>
            </TouchableOpacity>
          )}
        </View>

        {items.map((item, idx) =>
          editing ? (
            <View key={idx} style={s.itemEdit}>
              <View style={s.itemEditRow}>
                <TextInput
                  style={[s.itemInput, s.itemNameInput]}
                  value={item.name}
                  onChangeText={v => updateItem(idx, { name: v })}
                  placeholder="Item name"
                  placeholderTextColor={COLORS.textMuted}
                />
                <TouchableOpacity onPress={() => deleteItem(idx)} style={s.itemDelBtn}>
                  <Text style={s.itemDelText}>✕</Text>
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
              <View style={s.vatToggleRow}>
                <Text style={s.vatToggleLabel}>VAT Applicable</Text>
                <Switch
                  value={item.vat_applicable}
                  onValueChange={v => updateItem(idx, { vat_applicable: v })}
                  trackColor={{ false: COLORS.surface2, true: COLORS.accent + '88' }}
                  thumbColor={item.vat_applicable ? COLORS.accent : COLORS.textMuted}
                />
              </View>
            </View>
          ) : (
            <View key={item.id ?? idx} style={s.item}>
              <View style={s.itemMain}>
                <Text style={s.itemName} numberOfLines={2}>{item.name}</Text>
                {parseFloat(item.quantity) !== 1 && (
                  <Text style={s.itemQty}>×{item.quantity}</Text>
                )}
              </View>
              <View style={s.itemRight}>
                {!item.vat_applicable && <Text style={s.zeroTag}>0%</Text>}
                <Text style={s.itemPrice}>
                  {parseFloat(item.total_price) > 0
                    ? `${cur} ${parseFloat(item.total_price).toFixed(2)}`
                    : parseFloat(item.unit_price) > 0
                      ? `${cur} ${parseFloat(item.unit_price).toFixed(2)}`
                      : '—'}
                </Text>
              </View>
            </View>
          )
        )}
      </View>

      {/* Actions */}
      {editing ? (
        <View style={s.editActions}>
          <TouchableOpacity style={s.cancelBtn} onPress={cancelEdit}>
            <Text style={s.cancelText}>Cancel</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[s.saveBtn, saving && s.saveBtnDisabled]} onPress={save} disabled={saving}>
            {saving ? <ActivityIndicator color="#000" /> : <Text style={s.saveBtnText}>Save Changes</Text>}
          </TouchableOpacity>
        </View>
      ) : (
        <TouchableOpacity style={s.deleteBtn} onPress={del}>
          <Text style={s.deleteBtnText}>Delete Receipt</Text>
        </TouchableOpacity>
      )}
    </ScrollView>
  );
}

function VatRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={s.vatRow}>
      <Text style={s.vatLabel}>{label}</Text>
      <Text style={s.vatValue}>{value}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLORS.bg },
  content: { padding: 16, paddingBottom: 40 },
  center: { flex: 1, backgroundColor: COLORS.bg, alignItems: 'center', justifyContent: 'center' },
  empty: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 12 },
  titleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 },
  storeName: { color: COLORS.text, fontSize: 20, fontWeight: '700', flex: 1 },
  storeInput: { flex: 1, backgroundColor: COLORS.surface2, borderWidth: 1, borderColor: COLORS.accent, borderRadius: 3, color: COLORS.text, fontSize: 16, fontWeight: '700', padding: 8 },
  editBtn: { marginLeft: 12, borderWidth: 1, borderColor: COLORS.accent, borderRadius: 3, paddingHorizontal: 10, paddingVertical: 5 },
  editBtnText: { color: COLORS.accent, fontFamily: 'monospace', fontSize: 11 },
  metaGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 14 },
  metaCell: { backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 10, minWidth: '45%', flex: 1 },
  metaLabel: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 9, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 },
  metaValue: { color: COLORS.text, fontFamily: 'monospace', fontSize: 14, fontWeight: 'bold' },
  metaInput: { backgroundColor: COLORS.surface2, borderWidth: 1, borderColor: COLORS.accent, borderRadius: 3, color: COLORS.text, fontFamily: 'monospace', fontSize: 13, padding: 5 },
  vatBox: { backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 12, marginBottom: 14 },
  vatRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 },
  vatLabel: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 11 },
  vatValue: { color: COLORS.text, fontFamily: 'monospace', fontSize: 11 },
  section: { backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 14, marginBottom: 14 },
  sectionHeaderRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  sectionLabel: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5 },
  addItemBtn: { borderWidth: 1, borderColor: COLORS.accent, borderRadius: 3, paddingHorizontal: 8, paddingVertical: 4 },
  addItemBtnText: { color: COLORS.accent, fontFamily: 'monospace', fontSize: 10 },
  item: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: COLORS.border, paddingVertical: 10 },
  itemMain: { flex: 1, marginRight: 8 },
  itemName: { color: COLORS.text, fontSize: 13 },
  itemQty: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 10, marginTop: 2 },
  itemRight: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  zeroTag: { backgroundColor: COLORS.surface2, color: COLORS.green, fontFamily: 'monospace', fontSize: 9, paddingHorizontal: 4, paddingVertical: 2, borderRadius: 2 },
  itemPrice: { color: COLORS.accent, fontFamily: 'monospace', fontSize: 13, fontWeight: 'bold' },
  itemEdit: { borderBottomWidth: 1, borderBottomColor: COLORS.border, paddingVertical: 10, gap: 6 },
  itemEditRow: { flexDirection: 'row', gap: 6, alignItems: 'center' },
  itemNameInput: { flex: 1 },
  itemInput: { backgroundColor: COLORS.surface2, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, color: COLORS.text, padding: 7, fontFamily: 'monospace', fontSize: 12 },
  itemDelBtn: { paddingHorizontal: 8, paddingVertical: 6 },
  itemDelText: { color: COLORS.red, fontSize: 16 },
  miniField: { flex: 1 },
  miniLabel: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 8, textTransform: 'uppercase', marginBottom: 3 },
  vatToggleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingTop: 2 },
  vatToggleLabel: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 10 },
  editActions: { flexDirection: 'row', gap: 10 },
  cancelBtn: { flex: 1, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 4, padding: 14, alignItems: 'center' },
  cancelText: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 11 },
  saveBtn: { flex: 2, backgroundColor: COLORS.accent, borderRadius: 4, padding: 14, alignItems: 'center' },
  saveBtnDisabled: { opacity: 0.5 },
  saveBtnText: { color: '#000', fontFamily: 'monospace', fontSize: 12, fontWeight: 'bold', letterSpacing: 0.5 },
  deleteBtn: { borderWidth: 1, borderColor: COLORS.red, borderRadius: 4, padding: 14, alignItems: 'center' },
  deleteBtnText: { color: COLORS.red, fontFamily: 'monospace', fontSize: 12, letterSpacing: 0.5 },
});
