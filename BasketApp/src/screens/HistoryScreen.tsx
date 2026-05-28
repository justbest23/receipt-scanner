import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, FlatList, TouchableOpacity, StyleSheet, TextInput, ActivityIndicator, RefreshControl } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { api } from '../api/client';
import { COLORS } from '../theme';

export default function HistoryScreen() {
  const nav = useNavigation<any>();
  const [receipts, setReceipts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery] = useState('');
  const [skip, setSkip] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const LIMIT = 40;

  const load = useCallback(async (reset = false) => {
    const s = reset ? 0 : skip;
    try {
      const rows = await api.receipts(s, LIMIT);
      setReceipts(prev => reset ? rows : [...prev, ...rows]);
      setSkip(s + rows.length);
      setHasMore(rows.length === LIMIT);
    } catch {}
    finally { setLoading(false); setRefreshing(false); }
  }, [skip]);

  useEffect(() => { load(true); }, []);

  const onRefresh = () => { setRefreshing(true); load(true); };

  const filtered = receipts.filter(r =>
    !query || (r.store || '').toLowerCase().includes(query.toLowerCase()) || (r.date || '').includes(query)
  );

  const renderItem = ({ item }: { item: any }) => (
    <TouchableOpacity style={s.card} onPress={() => nav.navigate('ReceiptDetail', { id: item.id })}>
      <View style={s.cardTop}>
        <Text style={s.store} numberOfLines={1}>{item.store || 'Unknown Store'}</Text>
        <Text style={s.total}>R {(item.total ?? 0).toFixed(2)}</Text>
      </View>
      <View style={s.cardMeta}>
        <Text style={s.date}>{item.date || '—'}</Text>
        <Text style={s.items}>{item.item_count ?? 0} items</Text>
      </View>
    </TouchableOpacity>
  );

  return (
    <View style={s.root}>
      <View style={s.header}>
        <Text style={s.title}>History</Text>
        <Text style={s.count}>{filtered.length} receipts</Text>
      </View>
      <View style={s.searchWrap}>
        <TextInput
          style={s.search}
          placeholder="Filter by store or date…"
          placeholderTextColor={COLORS.textMuted}
          value={query}
          onChangeText={setQuery}
        />
      </View>
      {loading && !refreshing ? (
        <View style={s.center}><ActivityIndicator color={COLORS.accent} /></View>
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={r => String(r.id)}
          renderItem={renderItem}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.accent} />}
          ListEmptyComponent={<Text style={s.empty}>No receipts yet.{'\n'}Scan one to get started.</Text>}
          onEndReached={() => hasMore && load()}
          onEndReachedThreshold={0.3}
          ListFooterComponent={hasMore ? <ActivityIndicator color={COLORS.accent} style={{ margin: 16 }} /> : null}
          contentContainerStyle={filtered.length === 0 && s.emptyContainer}
        />
      )}
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLORS.bg },
  header: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', padding: 16, paddingBottom: 8 },
  title: { color: COLORS.text, fontFamily: 'monospace', fontSize: 16, letterSpacing: 1, textTransform: 'uppercase' },
  count: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 10 },
  searchWrap: { paddingHorizontal: 16, paddingBottom: 10 },
  search: { backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.border, borderRadius: 4, color: COLORS.text, padding: 10, fontFamily: 'monospace', fontSize: 13 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  emptyContainer: { flexGrow: 1, justifyContent: 'center' },
  empty: { textAlign: 'center', color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 12, lineHeight: 22 },
  card: { marginHorizontal: 16, marginBottom: 8, backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 14 },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  store: { color: COLORS.text, fontSize: 15, fontWeight: '600', flex: 1, marginRight: 8 },
  total: { color: COLORS.accent, fontFamily: 'monospace', fontSize: 14, fontWeight: 'bold' },
  cardMeta: { flexDirection: 'row', gap: 12 },
  date: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 10 },
  items: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 10 },
});
