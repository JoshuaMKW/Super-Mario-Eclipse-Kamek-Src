#include "sBmg.hxx"

using namespace SME;

String &Util::formatBMG(String &msg) {
    char buffer[32];

    OSCalendarTime calendarTime;
    OSTicksToCalendarTime(OSGetTime(), &calendarTime);

    SME::Class::TPlayerParams *playerData =
        SME::TGlobals::sGlobals.getPlayerParams(gpMarioAddress);

    msg.replaceAll("%name%", playerData->getPlayerName());
    msg.replaceAll("%shine%",
        String::intToString(TFlagManager::smInstance->Type4Flag.mShineCount, buffer));
    msg.replaceAll("%bcoin%",
        String::intToString(TFlagManager::smInstance->Type4Flag.mBlueCoinCount, buffer));
    msg.replaceAll("%rcoin%",
        String::intToString(TFlagManager::smInstance->Type6Flag.mRedCoinCount, buffer));
    msg.replaceAll("%coin%",
        String::intToString(TFlagManager::smInstance->Type4Flag.mGoldCoinCount, buffer));
    msg.replaceAll("%time%", SME::Util::Time::calendarToDate(calendarTime));
    msg.replaceAll("%date%", SME::Util::Time::calendarToTime(calendarTime));
    msg.replaceAll("%bdate%", SME::Util::Time::buildDate());
    msg.replaceAll("%btime%", SME::Util::Time::buildTime());
    msg.replaceAll("%cardslot%", gpCardManager->mChannel == CARD_SLOTA ? "A" : "B");

    return msg;
}