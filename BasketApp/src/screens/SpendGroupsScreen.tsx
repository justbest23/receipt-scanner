import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, FlatList, ScrollView, TouchableOpacity, StyleSheet,
  TextInput, Alert, ActivityIndicator, Modal,
} from 'react-native';
import { api } from '../api/client';
import { useAuth } from '../AuthContext';
import { COLORS } from '../theme';

type Tab = 'balance' | 'members';

export default function SpendGroupsScreen() {
  const { user } = useAuth();
  const [groups, setGroups] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [balance, setBalance] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>('balance');
  const [modal, setModal] = useState<'none' | 'create' | 'addMember'>('none');
  const [groupName, setGroupName] = useState('');
  const [groupDesc, setGroupDesc] = useState('');
  const [memberUsername, setMemberUsername] = useState('');
  const [saving, setSaving] = useState(false);

  const loadGroups = useCallback(async () => {
    try {
      const list = await api.spendGroups();
      setGroups(list);
      if (list.length > 0 && !selected) selectGroup(list[0]);
    } catch {}
    finally { setLoading(false); }
  }, []);

  const selectGroup = async (g: any) => {
    setSelected(g);
    setBalance(null);
    setTab('balance');
    try {
      const [detail, bal] = await Promise.all([api.spendGroup(g.id), api.spendGroupBalance(g.id)]);
      setSelected(detail);
      setBalance(bal);
    } catch {}
  };

  useEffect(() => { loadGroups(); }, []);

  const create = async () => {
    if (!groupName.trim()) { Alert.alert('Error', 'Name required'); return; }
    setSaving(true);
    try {
      await api.createSpendGroup({ name: groupName.trim(), description: groupDesc.trim() || undefined });
      setModal('none'); setGroupName(''); setGroupDesc('');
      setSelected(null);
      await loadGroups();
    } catch (e: any) { Alert.alert('Error', e.message); }
    finally { setSaving(false); }
  };

  const addMember = async () => {
    if (!memberUsername.trim() || !selected) { Alert.alert('Error', 'Username required'); return; }
    setSaving(true);
    try {
      await api.addSpendMember(selected.id, memberUsername.trim());
      setModal('none'); setMemberUsername('');
      const detail = await api.spendGroup(selected.id);
      setSelected(detail);
    } catch (e: any) { Alert.alert('Error', e.message); }
    finally { setSaving(false); }
  };

  const removeMember = (memberId: number, memberName: string) => {
    Alert.alert('Remove Member', `Remove ${memberName}?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Remove', style: 'destructive', onPress: async () => {
        await api.removeSpendMember(selected.id, memberId).catch(() => {});
        const detail = await api.spendGroup(selected.id).catch(() => null);
        if (detail) setSelected(detail);
      }},
    ]);
  };

  const leaveOrDelete = () => {
    if (!selected) return;
    const isOwner = selected.owner_id === user?.id;
    Alert.alert(
      isOwner ? 'Delete Group' : 'Leave Group',
      isOwner ? 'This will delete the group.' : 'You will lose access.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: isOwner ? 'Delete' : 'Leave', style: 'destructive', onPress: async () => {
          try {
            if (isOwner) await api.deleteSpendGroup(selected.id);
            else await api.removeSpendMember(selected.id, user!.id);
            setSelected(null);
            await loadGroups();
          } catch (e: any) { Alert.alert('Error', e.message); }
        }},
      ]
    );
  };

  if (loading) return <View style={s.center}><ActivityIndicator color={COLORS.accent} size="large" /></View>;

  if (groups.length === 0) {
    return (
      <View style={s.root}>
        <View style={s.emptyHeader}><Text style={s.title}>Spend Groups</Text></View>
        <View style={s.center}>
          <Text style={s.empty}>No spend groups yet.{'\n'}Create one to track shared expenses.</Text>
          <TouchableOpacity style={s.primaryBtn} onPress={() => setModal('create')}>
            <Text style={s.primaryBtnText}>Create Group</Text>
          </TouchableOpacity>
        </View>
        {renderModals()}
      </View>
    );
  }

  const members: any[] = selected?.members || [];
  const isOwner = selected?.owner_id === user?.id;
  const debts: any[] = balance?.debts || [];
  const myBalance = balance?.my_balance;

  const renderBalance = () => (
    <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 30 }}>
      {myBalance != null && (
        <View style={s.balCard}>
          <Text style={s.balLabel}>Your balance</Text>
          <Text style={[s.balValue, myBalance >= 0 ? s.balPositive : s.balNegative]}>
            {myBalance >= 0 ? '+' : ''}R {Math.abs(myBalance).toFixed(2)}
          </Text>
          <Text style={s.balHint}>
            {myBalance > 0 ? 'You are owed money' : myBalance < 0 ? 'You owe money' : 'All settled up!'}
          </Text>
        </View>
      )}

      {debts.length > 0 && (
        <View style={s.card}>
          <Text style={s.sectionLabel}>Who owes whom</Text>
          {debts.map((d: any, i: number) => (
            <View key={i} style={s.debtRow}>
              <Text style={s.debtFrom}>{d.from_name || d.from_username}</Text>
              <Text style={s.debtArrow}>→</Text>
              <Text style={s.debtTo}>{d.to_name || d.to_username}</Text>
              <Text style={s.debtAmount}>R {(d.amount ?? 0).toFixed(2)}</Text>
            </View>
          ))}
        </View>
      )}

      {debts.length === 0 && myBalance == null && (
        <View style={s.center}>
          <Text style={s.empty}>No balances to show yet.{'\n'}Link receipts to this group to track spending.</Text>
        </View>
      )}

      <View style={s.actionRow}>
        <TouchableOpacity style={[s.actionBtn, s.dangerBtn]} onPress={leaveOrDelete}>
          <Text style={[s.actionBtnText, { color: COLORS.red }]}>{isOwner ? 'Delete' : 'Leave'}</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );

  const renderMembers = () => (
    <View style={{ flex: 1 }}>
      <TouchableOpacity style={s.addMemberBtn} onPress={() => setModal('addMember')}>
        <Text style={s.addMemberText}>+ Add Member</Text>
      </TouchableOpacity>
      <FlatList
        data={members}
        keyExtractor={m => String(m.id)}
        contentContainerStyle={{ padding: 16, paddingBottom: 30 }}
        renderItem={({ item }) => (
          <View style={s.memberRow}>
            <View>
              <Text style={s.memberName}>{item.display_name || item.username}</Text>
              <Text style={s.memberMeta}>{item.username}{item.id === selected?.owner_id ? ' · owner' : ''}</Text>
            </View>
            {isOwner && item.id !== user?.id && (
              <TouchableOpacity onPress={() => removeMember(item.id, item.display_name || item.username)}>
                <Text style={s.removeText}>Remove</Text>
              </TouchableOpacity>
            )}
          </View>
        )}
      />
    </View>
  );

  function renderModals() {
    return (
      <>
        <Modal visible={modal === 'create'} transparent animationType="slide">
          <View style={s.overlay}>
            <View style={s.sheet}>
              <Text style={s.sheetTitle}>New Spend Group</Text>
              <TextInput style={s.input} value={groupName} onChangeText={setGroupName} placeholder="Group name" placeholderTextColor={COLORS.textMuted} />
              <TextInput style={[s.input, { height: 70 }]} value={groupDesc} onChangeText={setGroupDesc} placeholder="Description (optional)" placeholderTextColor={COLORS.textMuted} multiline />
              <View style={s.btnRow}>
                <TouchableOpacity style={s.cancelBtn} onPress={() => { setModal('none'); setGroupName(''); setGroupDesc(''); }}>
                  <Text style={s.cancelText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity style={s.saveBtn} onPress={create} disabled={saving}>
                  {saving ? <ActivityIndicator color="#000" /> : <Text style={s.saveBtnText}>Create</Text>}
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>

        <Modal visible={modal === 'addMember'} transparent animationType="slide">
          <View style={s.overlay}>
            <View style={s.sheet}>
              <Text style={s.sheetTitle}>Add Member</Text>
              <TextInput style={s.input} value={memberUsername} onChangeText={setMemberUsername} placeholder="Username" placeholderTextColor={COLORS.textMuted} autoCapitalize="none" />
              <View style={s.btnRow}>
                <TouchableOpacity style={s.cancelBtn} onPress={() => { setModal('none'); setMemberUsername(''); }}>
                  <Text style={s.cancelText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity style={s.saveBtn} onPress={addMember} disabled={saving}>
                  {saving ? <ActivityIndicator color="#000" /> : <Text style={s.saveBtnText}>Add</Text>}
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>
      </>
    );
  }

  return (
    <View style={s.root}>
      <View style={s.header}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          {groups.map(g => (
            <TouchableOpacity key={g.id} style={[s.groupTab, selected?.id === g.id && s.groupTabActive]} onPress={() => selectGroup(g)}>
              <Text style={[s.groupTabText, selected?.id === g.id && s.groupTabTextActive]}>{g.name}</Text>
            </TouchableOpacity>
          ))}
          <TouchableOpacity style={s.groupTab} onPress={() => setModal('create')}>
            <Text style={s.groupTabText}>+ New</Text>
          </TouchableOpacity>
        </ScrollView>
      </View>

      <View style={s.tabs}>
        {(['balance', 'members'] as Tab[]).map(t => (
          <TouchableOpacity key={t} style={[s.tabBtn, tab === t && s.tabBtnActive]} onPress={() => setTab(t)}>
            <Text style={[s.tabBtnText, tab === t && s.tabBtnTextActive]}>{t}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'balance' && renderBalance()}
      {tab === 'members' && renderMembers()}

      {renderModals()}
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32 },
  empty: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 12, textAlign: 'center', marginBottom: 20 },
  title: { color: COLORS.text, fontFamily: 'monospace', fontSize: 16, letterSpacing: 1, textTransform: 'uppercase' },
  emptyHeader: { padding: 16, paddingBottom: 8 },
  primaryBtn: { backgroundColor: COLORS.accent, borderRadius: 4, paddingVertical: 14, paddingHorizontal: 32, width: '100%', alignItems: 'center' },
  primaryBtnText: { color: '#000', fontFamily: 'monospace', fontSize: 13, fontWeight: 'bold' },
  header: { backgroundColor: COLORS.surface, borderBottomWidth: 1, borderBottomColor: COLORS.border, paddingVertical: 8, paddingHorizontal: 12 },
  groupTab: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 3, marginRight: 6 },
  groupTabActive: { backgroundColor: COLORS.accent },
  groupTabText: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 11 },
  groupTabTextActive: { color: '#000', fontWeight: 'bold' },
  tabs: { flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: COLORS.border },
  tabBtn: { flex: 1, paddingVertical: 10, alignItems: 'center' },
  tabBtnActive: { borderBottomWidth: 2, borderBottomColor: COLORS.accent },
  tabBtnText: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 10, textTransform: 'uppercase' },
  tabBtnTextActive: { color: COLORS.accent },
  balCard: { backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 20, marginBottom: 14, alignItems: 'center' },
  balLabel: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 },
  balValue: { fontFamily: 'monospace', fontSize: 28, fontWeight: 'bold', marginBottom: 4 },
  balPositive: { color: COLORS.green },
  balNegative: { color: COLORS.red },
  balHint: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 11 },
  card: { backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 14, marginBottom: 14 },
  sectionLabel: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 10 },
  debtRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: COLORS.border },
  debtFrom: { color: COLORS.text, fontSize: 13, flex: 1 },
  debtArrow: { color: COLORS.textMuted, marginHorizontal: 6 },
  debtTo: { color: COLORS.text, fontSize: 13, flex: 1 },
  debtAmount: { color: COLORS.accent, fontFamily: 'monospace', fontSize: 12 },
  actionRow: { flexDirection: 'row', gap: 10, marginTop: 4 },
  actionBtn: { flex: 1, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, padding: 12, alignItems: 'center' },
  dangerBtn: { borderColor: COLORS.red },
  actionBtnText: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 11 },
  addMemberBtn: { marginHorizontal: 16, marginTop: 12, borderWidth: 1, borderColor: COLORS.accent, borderRadius: 3, padding: 10, alignItems: 'center' },
  addMemberText: { color: COLORS.accent, fontFamily: 'monospace', fontSize: 11 },
  memberRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 14, marginBottom: 8 },
  memberName: { color: COLORS.text, fontSize: 14, marginBottom: 2 },
  memberMeta: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 10 },
  removeText: { color: COLORS.red, fontFamily: 'monospace', fontSize: 11 },
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: COLORS.surface, borderTopLeftRadius: 12, borderTopRightRadius: 12, padding: 20, paddingBottom: 36 },
  sheetTitle: { color: COLORS.text, fontFamily: 'monospace', fontSize: 14, letterSpacing: 1, textTransform: 'uppercase', marginBottom: 16 },
  input: { backgroundColor: COLORS.surface2, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, color: COLORS.text, padding: 10, fontFamily: 'monospace', fontSize: 13, marginBottom: 14 },
  btnRow: { flexDirection: 'row', gap: 10 },
  cancelBtn: { flex: 1, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, padding: 13, alignItems: 'center' },
  cancelText: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 11 },
  saveBtn: { flex: 1, backgroundColor: COLORS.accent, borderRadius: 3, padding: 13, alignItems: 'center' },
  saveBtnText: { color: '#000', fontFamily: 'monospace', fontSize: 11, fontWeight: 'bold' },
});
