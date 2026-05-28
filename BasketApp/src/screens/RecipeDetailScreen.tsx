import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity,
  ActivityIndicator, Alert, TextInput, Modal,
} from 'react-native';
import { useRoute } from '@react-navigation/native';
import { api } from '../api/client';
import { COLORS } from '../theme';

export default function RecipeDetailScreen() {
  const { params } = useRoute<any>();
  const [recipe, setRecipe] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [shoppingList, setShoppingList] = useState<any[] | null>(null);
  const [shoppingLoading, setShoppingLoading] = useState(false);
  const [editingInstructions, setEditingInstructions] = useState(false);
  const [instructions, setInstructions] = useState('');
  const [ingredientModal, setIngredientModal] = useState(false);
  const [ingName, setIngName] = useState('');
  const [ingQty, setIngQty] = useState('');
  const [ingUnit, setIngUnit] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.recipe(params.id);
      setRecipe(r);
      setInstructions(r.instructions || '');
    } catch { Alert.alert('Error', 'Failed to load recipe'); }
    finally { setLoading(false); }
  }, [params.id]);

  useEffect(() => { load(); }, []);

  const saveInstructions = async () => {
    setSaving(true);
    try {
      await api.setInstructions(params.id, instructions);
      setEditingInstructions(false);
      load();
    } catch (e: any) { Alert.alert('Error', e.message); }
    finally { setSaving(false); }
  };

  const addIngredient = async () => {
    if (!ingName.trim()) { Alert.alert('Error', 'Name required'); return; }
    setSaving(true);
    try {
      await api.addIngredient(params.id, {
        name: ingName.trim(),
        quantity: ingQty ? parseFloat(ingQty) : undefined,
        unit: ingUnit.trim() || undefined,
      });
      setIngredientModal(false);
      setIngName(''); setIngQty(''); setIngUnit('');
      load();
    } catch (e: any) { Alert.alert('Error', e.message); }
    finally { setSaving(false); }
  };

  const deleteIngredient = (id: number, name: string) => {
    Alert.alert('Remove', `Remove "${name}"?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Remove', style: 'destructive', onPress: async () => {
        await api.deleteIngredient(id).catch(() => {});
        load();
      }},
    ]);
  };

  const loadShopping = async () => {
    setShoppingLoading(true);
    try {
      const data = await api.shoppingList([params.id]);
      setShoppingList(data.items || []);
    } catch (e: any) { Alert.alert('Error', e.message); }
    finally { setShoppingLoading(false); }
  };

  if (loading) return <View style={s.center}><ActivityIndicator color={COLORS.accent} size="large" /></View>;
  if (!recipe) return <View style={s.center}><Text style={s.empty}>Recipe not found</Text></View>;

  const ingredients: any[] = recipe.ingredients || [];

  return (
    <ScrollView style={s.root} contentContainerStyle={s.content}>
      <Text style={s.recipeName}>{recipe.name}</Text>
      {recipe.description ? <Text style={s.desc}>{recipe.description}</Text> : null}

      {/* Ingredients */}
      <View style={s.section}>
        <View style={s.sectionHeader}>
          <Text style={s.sectionLabel}>Ingredients ({ingredients.length})</Text>
          <TouchableOpacity style={s.miniBtn} onPress={() => setIngredientModal(true)}>
            <Text style={s.miniBtnText}>+ Add</Text>
          </TouchableOpacity>
        </View>
        {ingredients.length === 0 ? (
          <Text style={s.hint}>No ingredients yet.</Text>
        ) : ingredients.map((ing: any) => (
          <View key={ing.id} style={s.ingRow}>
            <Text style={s.ingName}>{ing.name}</Text>
            <View style={s.ingRight}>
              {(ing.quantity || ing.unit) ? (
                <Text style={s.ingQty}>{ing.quantity ? `${ing.quantity}` : ''}{ing.unit ? ` ${ing.unit}` : ''}</Text>
              ) : null}
              {ing.price_estimate != null && (
                <Text style={s.ingPrice}>~R{ing.price_estimate.toFixed(2)}</Text>
              )}
              <TouchableOpacity onPress={() => deleteIngredient(ing.id, ing.name)}>
                <Text style={s.removeText}>✕</Text>
              </TouchableOpacity>
            </View>
          </View>
        ))}
      </View>

      {/* Instructions */}
      <View style={s.section}>
        <View style={s.sectionHeader}>
          <Text style={s.sectionLabel}>Instructions</Text>
          <TouchableOpacity style={s.miniBtn} onPress={() => setEditingInstructions(!editingInstructions)}>
            <Text style={s.miniBtnText}>{editingInstructions ? 'Cancel' : 'Edit'}</Text>
          </TouchableOpacity>
        </View>
        {editingInstructions ? (
          <>
            <TextInput
              style={s.instructionsInput}
              value={instructions}
              onChangeText={setInstructions}
              multiline
              placeholder="Write your instructions here…"
              placeholderTextColor={COLORS.textMuted}
            />
            <TouchableOpacity style={s.saveBtn} onPress={saveInstructions} disabled={saving}>
              {saving ? <ActivityIndicator color="#000" /> : <Text style={s.saveBtnText}>Save</Text>}
            </TouchableOpacity>
          </>
        ) : (
          <Text style={s.instructionsText}>
            {recipe.instructions || <Text style={s.hint}>No instructions yet.</Text>}
          </Text>
        )}
      </View>

      {/* Shopping List */}
      <View style={s.section}>
        <View style={s.sectionHeader}>
          <Text style={s.sectionLabel}>Shopping List</Text>
          <TouchableOpacity style={s.miniBtn} onPress={loadShopping} disabled={shoppingLoading}>
            {shoppingLoading ? <ActivityIndicator color={COLORS.accent} size="small" /> : <Text style={s.miniBtnText}>Generate</Text>}
          </TouchableOpacity>
        </View>
        {shoppingList === null ? (
          <Text style={s.hint}>Tap Generate to build a shopping list with price estimates.</Text>
        ) : shoppingList.length === 0 ? (
          <Text style={s.hint}>No items found.</Text>
        ) : shoppingList.map((item: any, i: number) => (
          <View key={i} style={s.shopRow}>
            <Text style={s.shopName}>{item.name}</Text>
            <View style={s.shopRight}>
              {item.quantity ? <Text style={s.shopQty}>{item.quantity}{item.unit ? ` ${item.unit}` : ''}</Text> : null}
              {item.estimated_price != null && (
                <Text style={s.shopPrice}>R{item.estimated_price.toFixed(2)}</Text>
              )}
            </View>
          </View>
        ))}
        {shoppingList && shoppingList.length > 0 && (
          <View style={s.shopTotal}>
            <Text style={s.shopTotalLabel}>Estimated Total</Text>
            <Text style={s.shopTotalValue}>
              R{shoppingList.reduce((sum: number, i: any) => sum + (i.estimated_price || 0), 0).toFixed(2)}
            </Text>
          </View>
        )}
      </View>

      {/* Add Ingredient Modal */}
      <Modal visible={ingredientModal} transparent animationType="slide">
        <View style={s.overlay}>
          <View style={s.sheet}>
            <Text style={s.sheetTitle}>Add Ingredient</Text>
            <Text style={s.fieldLabel}>Name</Text>
            <TextInput style={s.input} value={ingName} onChangeText={setIngName} placeholder="e.g. Chicken breast" placeholderTextColor={COLORS.textMuted} />
            <View style={s.twoCol}>
              <View style={{ flex: 1 }}>
                <Text style={s.fieldLabel}>Quantity</Text>
                <TextInput style={s.input} value={ingQty} onChangeText={setIngQty} placeholder="e.g. 500" placeholderTextColor={COLORS.textMuted} keyboardType="numeric" />
              </View>
              <View style={{ width: 12 }} />
              <View style={{ flex: 1 }}>
                <Text style={s.fieldLabel}>Unit</Text>
                <TextInput style={s.input} value={ingUnit} onChangeText={setIngUnit} placeholder="e.g. g, ml, cups" placeholderTextColor={COLORS.textMuted} />
              </View>
            </View>
            <View style={s.btnRow}>
              <TouchableOpacity style={s.cancelBtn} onPress={() => { setIngredientModal(false); setIngName(''); setIngQty(''); setIngUnit(''); }}>
                <Text style={s.cancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.saveBtn2} onPress={addIngredient} disabled={saving}>
                {saving ? <ActivityIndicator color="#000" /> : <Text style={s.saveBtnText}>Add</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLORS.bg },
  content: { padding: 16, paddingBottom: 40 },
  center: { flex: 1, backgroundColor: COLORS.bg, alignItems: 'center', justifyContent: 'center' },
  empty: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 12 },
  recipeName: { color: COLORS.text, fontSize: 20, fontWeight: '700', marginBottom: 6 },
  desc: { color: COLORS.textDim, fontSize: 13, marginBottom: 16, lineHeight: 20 },
  section: { backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 14, marginBottom: 14 },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  sectionLabel: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5 },
  miniBtn: { borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, paddingHorizontal: 8, paddingVertical: 4 },
  miniBtnText: { color: COLORS.accent, fontFamily: 'monospace', fontSize: 10 },
  hint: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 11, lineHeight: 18 },
  ingRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 7, borderBottomWidth: 1, borderBottomColor: COLORS.border },
  ingName: { color: COLORS.text, fontSize: 13, flex: 1 },
  ingRight: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  ingQty: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 11 },
  ingPrice: { color: COLORS.green, fontFamily: 'monospace', fontSize: 10 },
  removeText: { color: COLORS.red, fontSize: 13 },
  instructionsInput: { backgroundColor: COLORS.surface2, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, color: COLORS.text, padding: 10, fontFamily: 'monospace', fontSize: 12, minHeight: 120, textAlignVertical: 'top', marginBottom: 10 },
  instructionsText: { color: COLORS.text, fontSize: 13, lineHeight: 22 },
  saveBtn: { backgroundColor: COLORS.accent, borderRadius: 3, padding: 11, alignItems: 'center' },
  saveBtnText: { color: '#000', fontFamily: 'monospace', fontSize: 11, fontWeight: 'bold' },
  shopRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 7, borderBottomWidth: 1, borderBottomColor: COLORS.border },
  shopName: { color: COLORS.text, fontSize: 13, flex: 1 },
  shopRight: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  shopQty: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 10 },
  shopPrice: { color: COLORS.accent, fontFamily: 'monospace', fontSize: 11 },
  shopTotal: { flexDirection: 'row', justifyContent: 'space-between', paddingTop: 10, marginTop: 4 },
  shopTotalLabel: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 10, textTransform: 'uppercase' },
  shopTotalValue: { color: COLORS.accent, fontFamily: 'monospace', fontSize: 13, fontWeight: 'bold' },
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: COLORS.surface, borderTopLeftRadius: 12, borderTopRightRadius: 12, padding: 20, paddingBottom: 36 },
  sheetTitle: { color: COLORS.text, fontFamily: 'monospace', fontSize: 14, letterSpacing: 1, textTransform: 'uppercase', marginBottom: 16 },
  fieldLabel: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 9, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 5 },
  input: { backgroundColor: COLORS.surface2, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, color: COLORS.text, padding: 10, fontFamily: 'monospace', fontSize: 13, marginBottom: 14 },
  twoCol: { flexDirection: 'row' },
  btnRow: { flexDirection: 'row', gap: 10 },
  cancelBtn: { flex: 1, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, padding: 13, alignItems: 'center' },
  cancelText: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 11 },
  saveBtn2: { flex: 1, backgroundColor: COLORS.accent, borderRadius: 3, padding: 13, alignItems: 'center' },
});
