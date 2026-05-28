import React, { useState, useEffect } from 'react';
import { View, Text, ScrollView, StyleSheet, ActivityIndicator, TouchableOpacity, Dimensions } from 'react-native';
import { api } from '../api/client';
import { COLORS } from '../theme';

const W = Dimensions.get('window').width - 32;

export default function AnalyticsScreen() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.summary().then(setData).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <View style={s.center}><ActivityIndicator color={COLORS.accent} size="large" /></View>;
  if (!data) return <View style={s.center}><Text style={s.empty}>No data yet</Text></View>;

  const categories: any[] = data.by_category || [];
  const stores: any[] = data.by_store || [];
  const topItems: any[] = data.top_items || [];
  const maxCat = Math.max(...categories.map((c: any) => c.total), 1);
  const maxStore = Math.max(...stores.map((s: any) => s.total), 1);

  return (
    <ScrollView style={s.root} contentContainerStyle={s.content}>
      <Text style={s.title}>Insights</Text>

      {/* Summary row */}
      <View style={s.summaryRow}>
        <SummaryCard label="Total Spent" value={`R ${(data.total_spent ?? 0).toFixed(2)}`} />
        <SummaryCard label="Receipts" value={String(data.receipt_count ?? 0)} />
        <SummaryCard label="Avg Basket" value={`R ${(data.avg_basket ?? 0).toFixed(2)}`} />
      </View>

      {/* By Category */}
      {categories.length > 0 && (
        <View style={s.section}>
          <Text style={s.sectionLabel}>Spend by Category</Text>
          {categories.slice(0, 8).map((c: any) => (
            <View key={c.category} style={s.barRow}>
              <Text style={s.barLabel} numberOfLines={1}>{c.category || 'Uncategorised'}</Text>
              <View style={s.barTrack}>
                <View style={[s.barFill, { width: (c.total / maxCat) * (W - 120) }]} />
              </View>
              <Text style={s.barValue}>R {c.total.toFixed(0)}</Text>
            </View>
          ))}
        </View>
      )}

      {/* By Store */}
      {stores.length > 0 && (
        <View style={s.section}>
          <Text style={s.sectionLabel}>Spend by Store</Text>
          {stores.slice(0, 6).map((st: any) => (
            <View key={st.store} style={s.barRow}>
              <Text style={s.barLabel} numberOfLines={1}>{st.store || 'Unknown'}</Text>
              <View style={s.barTrack}>
                <View style={[s.barFill, s.barFillStore, { width: (st.total / maxStore) * (W - 120) }]} />
              </View>
              <Text style={s.barValue}>R {st.total.toFixed(0)}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Top Items */}
      {topItems.length > 0 && (
        <View style={s.section}>
          <Text style={s.sectionLabel}>Most Purchased Items</Text>
          {topItems.slice(0, 10).map((item: any, i: number) => (
            <View key={i} style={s.itemRow}>
              <Text style={s.itemRank}>#{i + 1}</Text>
              <Text style={s.itemName} numberOfLines={1}>{item.name}</Text>
              <Text style={s.itemCount}>{item.count}×</Text>
              <Text style={s.itemTotal}>R {item.total.toFixed(0)}</Text>
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <View style={s.summaryCard}>
      <Text style={s.summaryLabel}>{label}</Text>
      <Text style={s.summaryValue}>{value}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLORS.bg },
  content: { padding: 16, paddingBottom: 40 },
  center: { flex: 1, backgroundColor: COLORS.bg, alignItems: 'center', justifyContent: 'center' },
  empty: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 12 },
  title: { color: COLORS.text, fontFamily: 'monospace', fontSize: 16, letterSpacing: 1, textTransform: 'uppercase', marginBottom: 16 },
  summaryRow: { flexDirection: 'row', gap: 8, marginBottom: 20 },
  summaryCard: { flex: 1, backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 10 },
  summaryLabel: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 9, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 4 },
  summaryValue: { color: COLORS.accent, fontFamily: 'monospace', fontSize: 13, fontWeight: 'bold' },
  section: { backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 14, marginBottom: 16 },
  sectionLabel: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 12 },
  barRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 8 },
  barLabel: { color: COLORS.textDim, fontSize: 11, width: 80, marginRight: 6 },
  barTrack: { flex: 1, height: 6, backgroundColor: COLORS.surface2, borderRadius: 3, marginRight: 6 },
  barFill: { height: 6, backgroundColor: COLORS.accent, borderRadius: 3 },
  barFillStore: { backgroundColor: COLORS.purple },
  barValue: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 10, width: 50, textAlign: 'right' },
  itemRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: COLORS.border },
  itemRank: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 10, width: 24 },
  itemName: { flex: 1, color: COLORS.text, fontSize: 13, marginRight: 6 },
  itemCount: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 10, marginRight: 8 },
  itemTotal: { color: COLORS.accent, fontFamily: 'monospace', fontSize: 11 },
});
