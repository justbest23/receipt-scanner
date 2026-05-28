import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, ScrollView, FlatList, TouchableOpacity, StyleSheet,
  TextInput, Alert, ActivityIndicator, Modal,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { api } from '../api/client';
import { useAuth } from '../AuthContext';
import { COLORS } from '../theme';

type Tab = 'overview' | 'members' | 'receipts' | 'analytics';

export default function HouseholdScreen() {
  const { user } = useAuth();
  const nav = useNavigation<any>();
  const [households, setHouseholds] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [analytics, setAnalytics] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>('overview');
  const [modal, setModal] = useState<'none' | 'create' | 'join' | 'invite'>('none');
  const [householdName, setHouseholdName] = useState('');
  const [joinCode, setJoinCode] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const [saving, setSaving] = useState(false);

  const loadHouseholds = useCallback(async () => {
    try {
      const list = await api.households();
      setHouseholds(list);
      if (list.length > 0 && !selected) selectHousehold(list[0]);
    } catch {}
    finally { setLoading(false); }
  }, []);

  const selectHousehold = async (h: any) => {
    setSelected(h);
    setTab('overview');
    try {
      const [detail, anl] = await Promise.all([api.household(h.id), api.householdAnalytics(h.id)]);
      setSelected(detail);
      setAnalytics(anl);
    } catch {}
  };

  const loadHistory = useCallback(async () => {
    if (!selected) return;
    try { setHistory(await api.householdHistory(selected.id)); }
    catch {}
  }, [selected?.id]);

  useEffect(() => { loadHouseholds(); }, []);
  useEffect(() => { if (tab === 'receipts') loadHistory(); }, [tab]);

  const create = async () => {
    if (!householdName.trim()) { Alert.alert('Error', 'Name required'); return; }
    setSaving(true);
    try {
      await api.createHousehold(householdName.trim());
      setModal('none'); setHouseholdName('');
      setSelected(null);
      await loadHouseholds();
    } catch (e: any) { Alert.alert('Error', e.message); }
    finally { setSaving(false); }
  };

  const join = async () => {
    if (!joinCode.trim()) { Alert.alert('Error', 'Code required'); return; }
    setSaving(true);
    try {
      await api.joinHousehold(joinCode.trim());
      setModal('none'); setJoinCode('');
      setSelected(null);
      await loadHouseholds();
    } catch (e: any) { Alert.alert('Error', e.message); }
    finally { setSaving(false); }
  };

  const generateInvite = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      const res = await api.generateInvite(selected.id);
      setInviteCode(res.code || '');
      setModal('invite');
    } catch (e: any) { Alert.alert('Error', e.message); }
    finally { setSaving(false); }
  };

  const leaveOrDelete = () => {
    if (!selected) return;
    const isOwner = selected.owner_id === user?.id;
    Alert.alert(
      isOwner ? 'Delete Household' : 'Leave Household',
      isOwner ? 'This will delete the household for all members.' : 'You will lose access.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: isOwner ? 'Delete' : 'Leave', style: 'destructive', onPress: async () => {
          try {
            if (isOwner) await api.deleteHousehold(selected.id);
            else await api.leaveHousehold(selected.id);
            setSelected(null);
            await loadHouseholds();
          } catch (e: any) { Alert.alert('Error', e.message); }
        }},
      ]
    );
  };

  const removeMember = (memberId: number, memberName: string) => {
    Alert.alert('Remove Member', `Remove ${memberName}?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Remove', style: 'destructive', onPress: async () => {
        await api.removeMember(selected.id, memberId).catch(() => {});
        const detail = await api.household(selected.id).catch(() => null);
        if (detail) setSelected(detail);
      }},
    ]);
  };

  if (loading) return <View style={s.center}><ActivityIndicator color={COLORS.accent} size="large" /></View>;

  if (households.length === 0) {
    return (
      <View style={s.root}>
        <View style={s.emptyHeader}>
          <Text style={s.title}>Household</Text>
          <TouchableOpacity style={s.spendGroupsBtn} onPress={() => nav.navigate('SpendGroups')}>
            <Text style={s.spendGroupsBtnText}>Spend Groups →</Text>
          </TouchableOpacity>
        </View>
        <View style={s.center}>
          <Text style={s.empty}>You're not in a household yet.</Text>
          <TouchableOpacity style={s.primaryBtn} onPress={() => setModal('create')}>
            <Text style={s.primaryBtnText}>Create Household</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.secondaryBtn} onPress={() => setModal('join')}>
            <Text style={s.secondaryBtnText}>Join with Code</Text>
          </TouchableOpacity>
        </View>
        {renderModals()}
      </View>
    );
  }

  const members: any[] = selected?.members || [];
  const isOwner = selected?.owner_id === user?.id;

  const renderOverview = () => (
    <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 30 }}>
      <View style={s.card}>
        <Text style={s.cardLabel}>Household</Text>
        <Text style={s.cardValue}>{selected?.name}</Text>
        {selected?.description ? <Text style={s.cardDesc}>{selected.description}</Text> : null}
      </View>
      {analytics && (
        <View style={s.card}>
          <Text style={s.cardLabel}>Stats (30 days)</Text>
          <View style={s.statRow}>
            <StatCell label="Total Spent" value={`R ${(analytics.total_spent ?? 0).toFixed(2)}`} />
            <StatCell label="Receipts" value={String(analytics.receipt_count ?? 0)} />
          </View>
          <View style={s.statRow}>
            <StatCell label="Members" value={String(members.length)} />
            <StatCell label="Avg Basket" value={`R ${(analytics.avg_basket ?? 0).toFixed(2)}`} />
          </View>
        </View>
      )}
      <View style={s.actionRow}>
        <TouchableOpacity style={s.actionBtn} onPress={generateInvite} disabled={saving}>
          <Text style={s.actionBtnText}>📋 Invite</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[s.actionBtn, s.dangerBtn]} onPress={leaveOrDelete}>
          <Text style={[s.actionBtnText, { color: COLORS.red }]}>{isOwner ? 'Delete' : 'Leave'}</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );

  const renderMembers = () => (
    <FlatList
      data={members}
      keyExtractor={m => String(m.id)}
      contentContainerStyle={{ padding: 16, paddingBottom: 30 }}
      renderItem={({ item }) => (
        <View style={s.memberRow}>
          <View>
            <Text style={s.memberName}>{item.display_name || item.username}</Text>
            <Text style={s.memberRole}>{item.role || 'member'}{item.id === selected?.owner_id ? ' · owner' : ''}</Text>
          </View>
          {isOwner && item.id !== user?.id && (
            <TouchableOpacity onPress={() => removeMember(item.id, item.display_name || item.username)}>
              <Text style={s.removeText}>Remove</Text>
            </TouchableOpacity>
          )}
        </View>
      )}
    />
  );

  const renderReceipts = () => (
    <FlatList
      data={history}
      keyExtractor={r => String(r.id)}
      contentContainerStyle={{ padding: 16, paddingBottom: 30 }}
      ListEmptyComponent={<Text style={s.empty}>No receipts yet.</Text>}
      renderItem={({ item }) => (
        <View style={s.receiptRow}>
          <View style={s.receiptLeft}>
            <Text style={s.receiptStore}>{item.store || 'Unknown'}</Text>
            <Text style={s.receiptDate}>{item.date} · {item.uploaded_by_name || ''}</Text>
          </View>
          <Text style={s.receiptTotal}>R {(item.total ?? 0).toFixed(2)}</Text>
        </View>
      )}
    />
  );

  const renderAnalytics = () => {
    if (!analytics) return <View style={s.center}><ActivityIndicator color={COLORS.accent} /></View>;
    const byMember: any[] = analytics.by_member || [];
    const byStore: any[] = analytics.by_store || [];
    return (
      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 30 }}>
        {byMember.length > 0 && (
          <View style={s.card}>
            <Text style={s.cardLabel}>By Member</Text>
            {byMember.map((m: any) => (
              <View key={m.user_id} style={s.analyticsRow}>
                <Text style={s.analyticsName}>{m.display_name || m.username}</Text>
                <Text style={s.analyticsValue}>R {(m.total ?? 0).toFixed(2)}</Text>
              </View>
            ))}
          </View>
        )}
        {byStore.length > 0 && (
          <View style={s.card}>
            <Text style={s.cardLabel}>By Store</Text>
            {byStore.slice(0, 8).map((st: any) => (
              <View key={st.store} style={s.analyticsRow}>
                <Text style={s.analyticsName}>{st.store || 'Unknown'}</Text>
                <Text style={s.analyticsValue}>R {(st.total ?? 0).toFixed(2)}</Text>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    );
  };

  function renderModals() {
    return (
      <>
        <Modal visible={modal === 'create'} transparent animationType="slide">
          <View style={s.overlay}>
            <View style={s.sheet}>
              <Text style={s.sheetTitle}>Create Household</Text>
              <TextInput style={s.input} value={householdName} onChangeText={setHouseholdName} placeholder="Household name" placeholderTextColor={COLORS.textMuted} />
              <View style={s.btnRow}>
                <TouchableOpacity style={s.cancelBtn} onPress={() => { setModal('none'); setHouseholdName(''); }}>
                  <Text style={s.cancelText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity style={s.saveBtn} onPress={create} disabled={saving}>
                  {saving ? <ActivityIndicator color="#000" /> : <Text style={s.saveBtnText}>Create</Text>}
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>

        <Modal visible={modal === 'join'} transparent animationType="slide">
          <View style={s.overlay}>
            <View style={s.sheet}>
              <Text style={s.sheetTitle}>Join Household</Text>
              <TextInput style={s.input} value={joinCode} onChangeText={setJoinCode} placeholder="Invite code" placeholderTextColor={COLORS.textMuted} autoCapitalize="none" />
              <View style={s.btnRow}>
                <TouchableOpacity style={s.cancelBtn} onPress={() => { setModal('none'); setJoinCode(''); }}>
                  <Text style={s.cancelText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity style={s.saveBtn} onPress={join} disabled={saving}>
                  {saving ? <ActivityIndicator color="#000" /> : <Text style={s.saveBtnText}>Join</Text>}
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>

        <Modal visible={modal === 'invite'} transparent animationType="slide">
          <View style={s.overlay}>
            <View style={s.sheet}>
              <Text style={s.sheetTitle}>Invite Code</Text>
              <Text style={s.inviteCode}>{inviteCode}</Text>
              <Text style={s.hint}>Share this code with people you want to invite.</Text>
              <TouchableOpacity style={s.saveBtn} onPress={() => setModal('none')}>
                <Text style={s.saveBtnText}>Done</Text>
              </TouchableOpacity>
            </View>
          </View>
        </Modal>
      </>
    );
  }

  return (
    <View style={s.root}>
      <View style={s.topBar}>
        <Text style={s.topTitle}>Groups</Text>
        <TouchableOpacity style={s.spendGroupsBtn} onPress={() => nav.navigate('SpendGroups')}>
          <Text style={s.spendGroupsBtnText}>Spend Groups →</Text>
        </TouchableOpacity>
      </View>
      <View style={s.header}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          {households.map(h => (
            <TouchableOpacity key={h.id} style={[s.householdTab, selected?.id === h.id && s.householdTabActive]} onPress={() => selectHousehold(h)}>
              <Text style={[s.householdTabText, selected?.id === h.id && s.householdTabTextActive]}>{h.name}</Text>
            </TouchableOpacity>
          ))}
          <TouchableOpacity style={s.householdTab} onPress={() => setModal('create')}>
            <Text style={s.householdTabText}>+ New</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.householdTab} onPress={() => setModal('join')}>
            <Text style={s.householdTabText}>Join</Text>
          </TouchableOpacity>
        </ScrollView>
      </View>

      <View style={s.tabs}>
        {(['overview', 'members', 'receipts', 'analytics'] as Tab[]).map(t => (
          <TouchableOpacity key={t} style={[s.tabBtn, tab === t && s.tabBtnActive]} onPress={() => setTab(t)}>
            <Text style={[s.tabBtnText, tab === t && s.tabBtnTextActive]}>{t}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'overview' && renderOverview()}
      {tab === 'members' && renderMembers()}
      {tab === 'receipts' && renderReceipts()}
      {tab === 'analytics' && renderAnalytics()}

      {renderModals()}
    </View>
  );
}

function StatCell({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flex: 1, padding: 6 }}>
      <Text style={{ color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 9, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 3 }}>{label}</Text>
      <Text style={{ color: COLORS.accent, fontFamily: 'monospace', fontSize: 13, fontWeight: 'bold' }}>{value}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32 },
  empty: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 12, textAlign: 'center', marginBottom: 20 },
  title: { color: COLORS.text, fontFamily: 'monospace', fontSize: 16, letterSpacing: 1, textTransform: 'uppercase' },
  spendGroupsBtn: { paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3 },
  spendGroupsBtnText: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 10 },
  emptyHeader: { padding: 16, paddingBottom: 8, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  primaryBtn: { backgroundColor: COLORS.accent, borderRadius: 4, paddingVertical: 14, paddingHorizontal: 32, width: '100%', alignItems: 'center', marginBottom: 12 },
  primaryBtnText: { color: '#000', fontFamily: 'monospace', fontSize: 13, fontWeight: 'bold' },
  secondaryBtn: { borderWidth: 1, borderColor: COLORS.border2, borderRadius: 4, paddingVertical: 12, paddingHorizontal: 32, width: '100%', alignItems: 'center' },
  secondaryBtnText: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 12 },
  topBar: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: COLORS.border },
  topTitle: { color: COLORS.text, fontFamily: 'monospace', fontSize: 14, letterSpacing: 1, textTransform: 'uppercase' },
  header: { backgroundColor: COLORS.surface, borderBottomWidth: 1, borderBottomColor: COLORS.border, paddingVertical: 8, paddingHorizontal: 12 },
  householdTab: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 3, marginRight: 6 },
  householdTabActive: { backgroundColor: COLORS.accent },
  householdTabText: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 11 },
  householdTabTextActive: { color: '#000', fontWeight: 'bold' },
  tabs: { flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: COLORS.border },
  tabBtn: { flex: 1, paddingVertical: 10, alignItems: 'center' },
  tabBtnActive: { borderBottomWidth: 2, borderBottomColor: COLORS.accent },
  tabBtnText: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 10, textTransform: 'uppercase' },
  tabBtnTextActive: { color: COLORS.accent },
  card: { backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 14, marginBottom: 12 },
  cardLabel: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 },
  cardValue: { color: COLORS.text, fontSize: 16, fontWeight: '700', marginBottom: 4 },
  cardDesc: { color: COLORS.textDim, fontSize: 12, marginTop: 4 },
  statRow: { flexDirection: 'row', marginTop: 8 },
  actionRow: { flexDirection: 'row', gap: 10 },
  actionBtn: { flex: 1, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, padding: 12, alignItems: 'center' },
  dangerBtn: { borderColor: COLORS.red },
  actionBtnText: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 11 },
  memberRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 14, marginBottom: 8 },
  memberName: { color: COLORS.text, fontSize: 14, marginBottom: 2 },
  memberRole: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 10, textTransform: 'uppercase' },
  removeText: { color: COLORS.red, fontFamily: 'monospace', fontSize: 11 },
  receiptRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: COLORS.surface, borderRadius: 4, borderWidth: 1, borderColor: COLORS.border, padding: 14, marginBottom: 8 },
  receiptLeft: { flex: 1 },
  receiptStore: { color: COLORS.text, fontSize: 14, fontWeight: '600', marginBottom: 3 },
  receiptDate: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 10 },
  receiptTotal: { color: COLORS.accent, fontFamily: 'monospace', fontSize: 13, fontWeight: 'bold' },
  analyticsRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: COLORS.border },
  analyticsName: { color: COLORS.text, fontSize: 13, flex: 1 },
  analyticsValue: { color: COLORS.accent, fontFamily: 'monospace', fontSize: 12 },
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: COLORS.surface, borderTopLeftRadius: 12, borderTopRightRadius: 12, padding: 20, paddingBottom: 36 },
  sheetTitle: { color: COLORS.text, fontFamily: 'monospace', fontSize: 14, letterSpacing: 1, textTransform: 'uppercase', marginBottom: 16 },
  input: { backgroundColor: COLORS.surface2, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, color: COLORS.text, padding: 10, fontFamily: 'monospace', fontSize: 13, marginBottom: 14 },
  btnRow: { flexDirection: 'row', gap: 10 },
  cancelBtn: { flex: 1, borderWidth: 1, borderColor: COLORS.border2, borderRadius: 3, padding: 13, alignItems: 'center' },
  cancelText: { color: COLORS.textDim, fontFamily: 'monospace', fontSize: 11 },
  saveBtn: { flex: 1, backgroundColor: COLORS.accent, borderRadius: 3, padding: 13, alignItems: 'center' },
  saveBtnText: { color: '#000', fontFamily: 'monospace', fontSize: 11, fontWeight: 'bold' },
  inviteCode: { color: COLORS.accent, fontFamily: 'monospace', fontSize: 22, letterSpacing: 4, textAlign: 'center', padding: 16, backgroundColor: COLORS.surface2, borderRadius: 4, marginBottom: 12 },
  hint: { color: COLORS.textMuted, fontFamily: 'monospace', fontSize: 11, marginBottom: 16, lineHeight: 18 },
});
