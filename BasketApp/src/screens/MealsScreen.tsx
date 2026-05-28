import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, FlatList, TouchableOpacity, StyleSheet,
  TextInput, Alert, ActivityIndicator, Modal, ScrollView,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { api } from '../api/client';
import { COLORS } from '../theme';

export default function MealsScreen() {
  const nav = useNavigation<any>();
  const [recipes, setRecipes] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<'none' | 'create' | 'import'>('none');
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [url, setUrl] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try { setRecipes(await api.recipes()); }
    catch {}
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!name.trim()) { Alert.alert('Error', 'Name required'); return; }
    setSaving(true);
    try {
      await api.createRecipe({ name: name.trim(), description: desc.trim() || undefined });
      setModal('none'); setName(''); setDesc('');
      load();
    } catch (e: any) { Alert.alert('Error', e.message); }
    finally { setSaving(false); }
  };

  const importUrl = async () => {
    if (!url.trim()) { Alert.alert('Error', 'URL required'); return; }
    setSaving(true);
    try {
      await api.importRecipeUrl(url.trim());
      setModal('none'); setUrl('');
      load();
    } catch (e: any) { Alert.alert('Error', e.message); }
    finally { setSaving(false); }
  };

  const del = (id: number, recipeName: string) => {
    Alert.alert('Delete Recipe', `Delete "${recipeName}"?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: async () => {
        await api.deleteRecipe(id).catch(() => {});
        load();
      }},
    ]);
  };

  const renderItem = ({ item }: { item: any }) => (
    <TouchableOpacity style={s.card} onPress={() => nav.navigate('RecipeDetail', { id: item.id })}>
      <View style={s.cardTop}>
        <Text style={s.cardName} numberOfLines={1}>{item.name}</Text>
        <TouchableOpacity onPress={() => del(item.id, item.name)} style={s.delBtn}>
          <Text style={s.delText}>✕</Text>
        </TouchableOpacity>
      </View>
      {item.description ? <Text style={s.cardDesc} numberOfLines={2}>{item.description}</Text> : null}
      <View style={s.cardMeta}>
        <Text style={s.metaText}>{(item.ingredients || []).length} ingredients</Text>
        {item.servings ? <Text style={s.metaText}>{item.servings} servings</Text> : null}
      </View>
    </TouchableOpacity>
  );

  return (
    <View style={s.root}>
      <View style={s.header}>
        <Text style={s.title}>Meals</Text>
        <View style={s.headerBtns}>
          <TouchableOpacity style={s.iconBtn} onPress={() => setModal('import')}>
            <Text style={s.iconBtnText}>🔗</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.addBtn} onPress={() => setModal('create')}>
            <Text style={s.addBtnText}>+ Recipe</Text>
          </TouchableOpacity>
        </View>
      </View>

      {loading ? (
        <View style={s.center}><ActivityIndicator color={COLORS.accent} /></View>
      ) : (
        <FlatList
          data={recipes}
          keyExtractor={r => String(r.id)}
          renderItem={renderItem}
          ListEmptyComponent={
            <View style={s.emptyContainer}>
              <Text style={s.empty}>No recipes yet.{'\n'}Create one or import from a URL.</Text>
            </View>
          }
          contentContainerStyle={recipes.length === 0 ? { flexGrow: 1 } : { paddingBottom: 20 }}
        />
      )}

      {/* Create Modal */}
      <Modal visible={modal === 'create'} transparent animationType="slide">
        <View style={s.overlay}>
          <View style={s.sheet}>
            <Text style={s.sheetTitle}>New Recipe</Text>
            <Text style={s.label}>Name</Text>
            <TextInput style={s.input} value={name} onChangeText={setName} placeholder="Recipe name" placeholderTextColor={COLORS.textMuted} />
            <Text style={s.label}>Description (optional)</Text>
            <TextInput style={[s.input, { height: 80 }]} value={desc} onChangeText={setDesc} placeholder="Brief description…" placeholderTextColor={COLORS.textMuted} multiline />
            <View style={s.row}>
              <TouchableOpacity style={s.cancelBtn} onPress={() => { setModal('none'); setName(''); setDesc(''); }}>
                <Text style={s.cancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.saveBtn} onPress={create} disabled={saving}>
                {saving ? <ActivityIndicator color="#000" /> : <Text style={s.saveBtnText}>Create</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Import Modal */}
      <Modal visible={modal === 'import'} transparent animationType="slide">
        <View style={s.overlay}>
          <View style={s.sheet}>
            <Text style={s.sheetTitle}>Import from URL</Text>
            <Text style={s.label}>Recipe URL</Text>
            <TextInput style={s.input} value={url} onChangeText={setUrl} placeholder="https://…" placeholderTextColor={COLORS.textMuted} autoCapitalize="none" keyboardType="url" />
            <View style={s.row}>
              <TouchableOpacity style={s.cancelBtn} onPress={() => { setModal('none'); setUrl(''); }}>
                <Text style={s.cancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.saveBtn} onPress={importUrl} disabled={saving}>
                {saving ? <ActivityIndicator color="#000" /> : <Text style={s.saveBtnText}>Import</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLORS.bg },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, paddingBottom: 8 },
  title: { color: COLORS.text, fontFamily: 'monospace', fontSize: 16, letterSpacing: 1, textTransform: 'uppercase' },
  headerBtns: { flexDirection: 'row', gap: 8 },
  iconBtn: { padding: 8 },
  iconBtnText: { fontSize: 18 },
  addBtn: { backgroundColor: COLORS.accent, borderRadius: 3, paddingHorizontal: 12, paddingVertical: 7 },
  addBtnText: { color: '#000', fontFamily: 'monospace', fontSize: 11, fontWeight: 'bold' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  emptyContainer: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  empty: { textAlign: 'center', color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 12, lineHeight: 22 },
  card: { marginHorizontal: 16, marginBottom: 10, backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 14 },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  cardName: { color: COLORS.text, fontSize: 15, fontWeight: '600', flex: 1 },
  cardDesc: { color: COLORS.textDim, fontSize: 12, marginBottom: 8, lineHeight: 18 },
  cardMeta: { flexDirection: 'row', gap: 12 },
  metaText: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 10 },
  delBtn: { padding: 4 },
  delText: { color: COLORS.red, fontSize: 14 },
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: COLORS.surface, borderTopLeftRadius: 12, borderTopRightRadius: 12, padding: 20, paddingBottom: 36 },
  sheetTitle: { color: COLORS.text, fontFamily: 'monospace', fontSize: 14, letterSpacing: 1, textTransform: 'uppercase', marginBottom: 16 },
  label: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 9, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 5 },
  input: { backgroundColor: COLORS.surface2, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, color: COLORS.text, padding: 10, fontFamily: 'monospace', fontSize: 13, marginBottom: 14 },
  row: { flexDirection: 'row', gap: 10 },
  cancelBtn: { flex: 1, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, padding: 13, alignItems: 'center' },
  cancelText: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 11 },
  saveBtn: { flex: 1, backgroundColor: COLORS.accent, borderRadius: 3, padding: 13, alignItems: 'center' },
  saveBtnText: { color: '#000', fontFamily: 'monospace', fontSize: 11, fontWeight: 'bold' },
});
