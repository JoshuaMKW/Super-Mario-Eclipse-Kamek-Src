#include "types.h"
#include "OS.h"
#include "sms/JSystem/JDrama.hxx"
#include "sms/JSystem/J2D/J2DTextbox.hxx"

#include "SME.hxx"

using namespace SME;

Class::TCheatHandler gDebugModeHandler;

static u16 gDebugModeCheatCode[] = {TMarioGamePad::Buttons::DPAD_UP,
                                    TMarioGamePad::Buttons::DPAD_UP,
                                    TMarioGamePad::Buttons::DPAD_DOWN,
                                    TMarioGamePad::Buttons::DPAD_DOWN,
                                    TMarioGamePad::Buttons::DPAD_LEFT,
                                    TMarioGamePad::Buttons::DPAD_RIGHT,
                                    TMarioGamePad::Buttons::DPAD_LEFT,
                                    TMarioGamePad::Buttons::DPAD_RIGHT,
                                    TMarioGamePad::Buttons::B,
                                    TMarioGamePad::Buttons::A,
                                    TMarioGamePad::Buttons::START};

J2DTextBox *gDebugTextBox;

static void debugModeNotify(Class::TCheatHandler *)
{
    if (gpMSound->gateCheck(MSound::SE_SHINE_TOUCH))
        startSoundActor__Q214MSoundSESystem8MSoundSEFUlPC3VecUlPP8JAISoundUlUc(gpMSound,
                                                                               MSound::SE_SHINE_TOUCH,
                                                                               0, 0, 0, 4);

    Memory::PPC::write<u32>((void *)0x802A6788, 0x3BC00009);

    #ifndef SME_DEBUG
        gDebugTextBox->isVisible = true;
    #endif
}

// extern runtime_mods.cpp
void Patch::Cheat::drawCheatText()
{
    if (gDebugTextBox && gDebugTextBox->getStringPtr())
    {
        #ifndef SME_DEBUG
            if (*gDebugTextBox->getStringPtr() != '\0' && gDebugModeHandler.isActive())
        #else
            if (*gDebugTextBox->getStringPtr() != '\0')
        #endif
        {
            gDebugTextBox->draw(250, 24);
        }
    }
}


// 0x80295B6C
// extern -> SME.cpp
void *Patch::Cheat::handleDebugCheat(void *GCLogoDir)
{
    if (!gDebugModeHandler.isInitialized())
    {
        gDebugModeHandler.setGamePad(gpApplication.mGamePad1);
        gDebugModeHandler.setInputList(gDebugModeCheatCode);
        gDebugModeHandler.setSuccessCallBack(&debugModeNotify);
    }
    gDebugModeHandler.advanceInput();
    return GCLogoDir;
}