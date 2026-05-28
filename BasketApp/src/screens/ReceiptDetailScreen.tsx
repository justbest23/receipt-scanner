import React, { useState, useEffect } from 'react';
import { View, Text, ScrollView, StyleSheet, ActivityIndicator, TouchableOpacity, Alert } from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import { api } from '../api/client';
import { COLORS } from '../theme';

export default function ReceiptDetailScreen() {
  const nav = useNavigation<any>();
  const { params } = useRoute<any>();
  const [receipt, setReceipt] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.receipt(params.id).then(setReceipt).catch(() => Alert.alert('Error', 'Failed to load receipt')).finally(() => setLoading(false));
  }, [params.id]);

  const del = () => {
    Alert.alert('Delete Receipt', 'Are you sure?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: async () => {
        await api.deleteReceipt(params.id).catch(() => {});
        nav.goBack();
      }},
    ]);
  };

  if (loading) return <View style={s.center}><ActivityIndicator color={COLORS.accent} size="large" /></View>;
  if (!receipt) return <View style={s.center}><Text style={s.empty}>Receipt not found</Text></View>;

  const items: any[] = receipt.items || [];
  const taxable = items.filter(i => i.vat_applicable).reduce((s: number, i: any) => s + (i.total_price ?? 0), 0);
  const zeroRated = items.filter(i => !i.vat_applicable).reduce((s: number, i: any) => s + (i.total_price ?? 0), 0);

  return (
    <ScrollView style={s.root} contentContainerStyle={s.content}>
      {/* Header */}
      <View style={s.storeBadge}>
        <Text style={s.storeName}>{receipt.store || 'Unknown Store'}</Text>
        <TouchableOpacity onPress={del} style={s.delBtn}><Text style={s.delText}>Delete</Text></TouchableOpacity>
      </View>

      <View style={s.metaGrid}>
        <MetaCell label="Date" value={receipt.date || '—'} />
        <MetaCell label="Total" value={`R ${(receipt.total ?? 0).toFixed(2)}`} accent />
        <MetaCell label="VAT" value={receipt.vat_amount != null ? `R ${receipt.vat_amount.toFixed(2)}` : '—'} />
        <MetaCell label="Items" value={String(items.length)} />
      </View>

      {taxable > 0 || zeroRated > 0 ? (
        <View style={s.vatBreak}>
          <Text style={s.sectionLabel}>VAT Breakdown</Text>
          {taxable > 0 && <Row label="Taxable (15%)" value={`R ${taxable.toFixed(2)}`} />}
          {zeroRated > 0 && <Row label="Zero-rated" value={`R ${zeroRated.toFixed(2)}`} />}
        </View>
      ) : null}

      <Text style={s.sectionLabel}>Line Items</Text>
      {items.map((item, i) => (
        <View key={i} style={s.item}>
          <View style={s.itemMain}>
            <Text style={s.itemName} numberOfLines={2}>{item.name || item.receipt_name}</Text>
            {item.quantity && item.quantity !== 1 && (
              <Text style={s.itemQty}>×{item.quantity}</Text>
            )}
          </View>
          <View style={s.itemRight}>
            {!item.vat_applicable && <Text style={s.zeroTag}>0%</Text>}
            <Text style={s.itemPrice}>R {(item.total_price ?? item.unit_price ?? 0).toFixed(2)}</Text>
          </View>
        </View>
      ))}
    </ScrollView>
  );
}

function MetaCell({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <View style={s.metaCell}>
      <Text style={s.metaLabel}>{label}</Text>
      <Text style={[s.metaValue, accent && { color: COLORS.accent }]}>{value}</Text>
    </View>
  );
}
function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={s.row}>
      <Text style={s.rowLabel}>{label}</Text>
      <Text style={s.rowValue}>{value}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLORS.bg },
  content: { padding: 16, paddingBottom: 40 },
  center: { flex: 1, backgroundColor: COLORS.bg, alignItems: 'center', justifyContent: 'center' },
  empty: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 12 },
  storeBadge: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 },
  storeName: { color: COLORS.text, fontSize: 18, fontWeight: '700', flex: 1 },
  delBtn: { padding: 6 },
  delText: { color: COLORS.red, fontFamily: 'monospace', fontSize: 11 },
  metaGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 },
  metaCell: { backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 10, minWidth: '45%', flex: 1 },
  metaLabel: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 9, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 },
  metaValue: { color: COLORS.text, fontFamily: 'monospace', fontSize: 14, fontWeight: 'bold' },
  vatBreak: { backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 12, marginBottom: 16 },
  sectionLabel: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 },
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 },
  rowLabel: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 11 },
  rowValue: { color: COLORS.text, fontFamily: 'monospace', fontSize: 11 },
  item: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: COLORS.border, paddingVertical: 10 },
  itemMain: { flex: 1, marginRight: 8 },
  itemName: { color: COLORS.text, fontSize: 13 },
  itemQty: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 10, marginTop: 2 },
  itemRight: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  zeroTag: { backgroundColor: COLORS.surface2, color: COLORS.green, fontFamily: 'monospace', fontSize: 9, paddingHorizontal: 4, paddingVertical: 2, borderRadius: 2 },
  itemPrice: { color: COLORS.accent, fontFamily: 'monospace', fontSize: 13, fontWeight: 'bold' },
});
