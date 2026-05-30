import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Text } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import LoginScreen from '../screens/LoginScreen';
import ScanScreen from '../screens/ScanScreen';
import HistoryScreen from '../screens/HistoryScreen';
import ReceiptDetailScreen from '../screens/ReceiptDetailScreen';
import AnalyticsScreen from '../screens/AnalyticsScreen';
import ProfileScreen from '../screens/ProfileScreen';
import MealsScreen from '../screens/MealsScreen';
import RecipeDetailScreen from '../screens/RecipeDetailScreen';
import HouseholdScreen from '../screens/HouseholdScreen';
import SpendGroupsScreen from '../screens/SpendGroupsScreen';
import { useAuth } from '../AuthContext';
import { COLORS } from '../theme';

const Stack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();

const ICONS: Record<string, string> = {
  Scan: '📷',
  History: '🧾',
  Meals: '🍽',
  Groups: '👥',
  Insights: '📊',
  Profile: '👤',
};

function TabIcon({ name, focused }: { name: string; focused: boolean }) {
  return <Text style={{ fontSize: 19, opacity: focused ? 1 : 0.45 }}>{ICONS[name] ?? '•'}</Text>;
}

const STACK_HEADER = {
  headerStyle: { backgroundColor: COLORS.surface },
  headerTintColor: COLORS.text,
  headerTitleStyle: { fontFamily: 'monospace', fontSize: 13, letterSpacing: 1 },
};

function MainTabs() {
  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: COLORS.bg }}>
      <Tab.Navigator
        screenOptions={({ route }) => ({
          headerShown: false,
          tabBarIcon: ({ focused }) => <TabIcon name={route.name} focused={focused} />,
          tabBarStyle: { backgroundColor: COLORS.surface, borderTopColor: COLORS.border },
          tabBarActiveTintColor: COLORS.accent,
          tabBarInactiveTintColor: COLORS.textDim,
          tabBarLabelStyle: { fontFamily: 'monospace', fontSize: 9, letterSpacing: 0.5 },
        })}>
        <Tab.Screen name="Scan" component={ScanScreen} />
        <Tab.Screen name="History" component={HistoryScreen} />
        <Tab.Screen name="Meals" component={MealsScreen} />
        <Tab.Screen name="Groups" component={GroupsStack} />
        <Tab.Screen name="Profile" component={ProfileScreen} />
      </Tab.Navigator>
    </SafeAreaView>
  );
}

const GroupsTabStack = createNativeStackNavigator();
function GroupsStack() {
  return (
    <GroupsTabStack.Navigator screenOptions={{ headerShown: false }}>
      <GroupsTabStack.Screen name="Household" component={HouseholdScreen} />
      <GroupsTabStack.Screen name="SpendGroups" component={SpendGroupsScreen}
        options={{ headerShown: true, title: 'SPEND GROUPS', ...STACK_HEADER }} />
    </GroupsTabStack.Navigator>
  );
}

export default function AppNavigator() {
  const { user } = useAuth();
  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {user ? (
          <>
            <Stack.Screen name="Main" component={MainTabs} />
            <Stack.Screen name="ReceiptDetail" component={ReceiptDetailScreen}
              options={{ headerShown: true, title: 'RECEIPT', ...STACK_HEADER }} />
            <Stack.Screen name="RecipeDetail" component={RecipeDetailScreen}
              options={{ headerShown: true, title: 'RECIPE', ...STACK_HEADER }} />
            <Stack.Screen name="Insights" component={AnalyticsScreen}
              options={{ headerShown: true, title: 'INSIGHTS', ...STACK_HEADER }} />
          </>
        ) : (
          <Stack.Screen name="Login" component={LoginScreen} />
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
}
