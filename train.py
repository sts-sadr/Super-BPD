import torch
import torch.nn as nn
from model import VGG16
from vis_flux import vis_flux
from datasets import FluxSegmentationDataset
from torch.utils.data import Dataset, DataLoader

INI_LEARNING_RATE = 1e-5
WEIGHT_DECAY = 5e-4
EPOCHES = 1e5
#DATASET = 'BSDS500'
DATASET = 'PascalContext'
SNAPSHOT_DIR = './snapshots/'
TRAIN_DEBUG_VIS_DIR = './train_debug_vis/' + DATASET

def loss_calc(pred_flux, gt_flux, weight_matrix):

    device_id = pred_flux.device
    weight_matrix = weight_matrix.cuda(device_id)
    gt_flux = gt_flux.cuda(device_id)

    gt_flux = 0.999999 * gt_flux / (gt_flux.norm(p=2, dim=1) + 1e-9)

    # norm loss
    norm_loss = weight_matrix * (pred_flux - gt_flux)**2
    norm_loss = norm_loss.sum()

    # angle loss
    pred_flux = 0.999999 * pred_flux / (pred_flux.norm(p=2, dim=1) + 1e-9)

    angle_loss = weight_matrix * (torch.acos(torch.sum(pred_flux * gt_flux, dim=1)))**2
    angle_loss = angle_loss.sum()

    return norm_loss, angle_loss

def get_params(model, key, bias=False):
    # for backbone 
    if key == "backbone":
        for m in model.named_modules():
            if "backbone" in m[0]:
                if isinstance(m[1], nn.Conv2d):
                    if not bias:
                        yield m[1].weight
                    else:
                        yield m[1].bias
    # for added layer
    if key == "added":
        for m in model.named_modules():
            if "backbone" not in m[0]:
                if isinstance(m[1], nn.Conv2d):
                    if not bias:
                        yield m[1].weight
                    else:
                        yield m[1].bias


def adjust_learning_rate(optimizer, step):
    
    if step == 8e4:
        for param_group in optimizer.param_groups:
            param_group['lr'] *= 0.1

def main():

    if not os.path.exists(SNAPSHOT_DIR):
        os.makedirs(SNAPSHOT_DIR)

    if not os.path.exists(TRAIN_DEBUG_VIS_DIR):
        os.makedirs(TRAIN_DEBUG_VIS_DIR)

    model = VGG16()

    saved_dict = torch.load('vgg16_pretrain.pth')
    model_dict = model.state_dict()
    saved_key = list(saved_dict.keys())
    model_key = list(model_dict.keys())

    for i in range(26):
        model_dict[model_key[i]] = saved_dict[saved_key[i]]
    
    model.load_state_dict(model_dict)

    model.train()
    model.cuda()
    
    optimizer = torch.optim.Adam(
        params=[
            {
                "params": get_params(model, key="backbone", bias=False),
                "lr": INI_LEARNING_RATE
            },
            {
                "params": get_params(model, key="backbone", bias=True),
                "lr": 2 * INI_LEARNING_RATE
            },
            {
                "params": get_params(model, key="added", bias=False),
                "lr": 10 * INI_LEARNING_RATE  
            },
            {
                "params": get_params(model, key="added", bias=True),
                "lr": 20 * INI_LEARNING_RATE   
            },
        ],
        weight_decay=WEIGHT_DECAY
    )

    dataloader = DataLoader(FluxSegmentationDataset(dataset=DATASET, mode='train'), batch_size=1, shuffle=True, num_workers=4)

    global_step = 0

    for epoch in range(1, EPOCHES):

        for i_iter, batch_data in enumerate(dataloader):

            global_step += 1

            Input_image, vis_image, gt_mask, gt_flux, weight_matrix, dataset_lendth, image_name = batch_data

            optimizer.zero_grad()

            pred_flux = model(Input_image.cuda())

            norm_loss, angle_loss = loss_calc(pred_flux, gt_flux, weight_matrix)

            total_loss = norm_loss + angle_loss

            total_loss.backward()

            optimizer.step()

            if global_step % 100 == 0:
                print('epoche {} i_iter/total {}/{} norm_loss {:.2f} angle_loss {:.2f}'.format(\
                       epoch, i_iter, int(dataset_lendth.data), norm_loss, angle_loss))
                
            if global_step % 500 == 0:
                vis_flux(vis_image, pred_flux, gt_flux, gt_mask, image_name, TRAIN_DEBUG_VIS_DIR)

            if global_step % 1e4 == 0:
                torch.save(model.state_dict(), SNAPSHOT_DIR + DATASET + '_' + str(global_step) + '.pth')

if __name__ == '__main__':
    main()




